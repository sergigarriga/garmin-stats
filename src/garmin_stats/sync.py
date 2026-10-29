"""Sincronización: histórico completo la primera vez, solo lo nuevo después."""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from garmin_personal_api.errors import HttpError

from . import FIT_DIR
from .api import Api
from .store import Store

log = logging.getLogger(__name__)

# Días que se vuelven a pedir en cada sincronización: Garmin corrige datos recientes
# (sueño que se cierra tarde, HRV, pasos sincronizados después).
REFRESH_DAYS = 3


def _days(start: date, end: date, step: int):
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=step - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def _list(resp, *path):
    for p in path:
        resp = (resp or {}).get(p) if isinstance(resp, dict) else None
    return resp if isinstance(resp, list) else []


@dataclass
class RangeDataset:
    """Endpoint que acepta un rango de fechas y devuelve un registro por día."""

    name: str
    method: str
    chunk_days: int
    records: Callable[[object], list]
    date_field: str


RANGE_DATASETS = [
    RangeDataset("daily_summary", "get_daily_summaries", 365, lambda r: _list(r, "data"), "calendarDate"),
    RangeDataset("hrv", "get_daily_hrv_summaries", 365, lambda r: _list(r, "hrvSummaries"), "calendarDate"),
    RangeDataset("sleep", "get_daily_sleep_summaries", 28, lambda r: r if isinstance(r, list) else [], "calendarDate"),
    RangeDataset("body_battery", "get_daily_body_battery", 28, lambda r: r if isinstance(r, list) else [], "date"),
    RangeDataset("weight", "get_weight_measurements", 28, lambda r: _list(r, "dailyWeightSummaries"), "summaryDate"),
    RangeDataset("hydration", "get_daily_hydration", 28, lambda r: r if isinstance(r, list) else [], "calendarDate"),
]


class Syncer:
    def __init__(self, api: Api, store: Store, intraday: bool = True, fit: bool = True) -> None:
        self.api = api
        self.store = store
        self.intraday = intraday
        self.fit = fit
        self.today = date.today()

    # ---------- utilidades ----------
    def _fetch_range(self, ds: RangeDataset, start: date, end: date) -> int:
        """Pide un rango. Si Garmin dice 400 (rango demasiado largo), lo parte en dos."""
        try:
            resp = self.api.call(ds.method, start, end)
        except HttpError as e:
            if e.status_code == 400 and start < end:
                mid = start + (end - start) // 2
                return self._fetch_range(ds, start, mid) + self._fetch_range(ds, mid + timedelta(days=1), end)
            raise
        n = 0
        for rec in ds.records(resp):
            key = rec.get(ds.date_field) if isinstance(rec, dict) else None
            if key:
                self.store.put(ds.name, key, rec)
                n += 1
        return n

    # ---------- inicio del histórico ----------
    def first_date(self, activities: list[dict]) -> date:
        saved = self.store.state("first_date")
        if saved:
            return date.fromisoformat(saved)
        log.info("Busco desde cuándo hay datos (año a año hacia atrás)...")
        earliest = self.today
        empty_years = 0
        end = self.today
        while empty_years < 2 and end.year > 2005:
            start = end - timedelta(days=364)
            recs = _list(self.api.call("get_daily_summaries", start, end), "data")
            dates = [r["calendarDate"] for r in recs if r.get("calendarDate")]
            if dates:
                earliest = min(earliest, date.fromisoformat(min(dates)))
                empty_years = 0
            else:
                empty_years += 1
            end = start - timedelta(days=1)
        for a in activities:
            d = date.fromisoformat(a["startTimeLocal"][:10])
            earliest = min(earliest, d)
        self.store.set_state("first_date", earliest.isoformat())
        log.info("Primer dato: %s", earliest)
        return earliest

    # ---------- bloques ----------
    def sync_profile(self) -> None:
        self.store.put("profile", "settings", self.api.call("get_user_profile_settings"))
        self.store.put("profile", "hr_zones", self.api.call("get_heart_rate_zones"))
        try:
            self.store.put("fitness_age", self.today.isoformat(), self.api.call("get_fitness_age", self.today))
        except HttpError as e:
            log.warning("Edad física no disponible (HTTP %s)", e.status_code)

    def sync_activities(self) -> list[dict]:
        acts: list[dict] = []
        start = 0
        while True:
            page = self.api.call("search_activities", start=start, limit=100) or []
            acts += page
            if len(page) < 100:
                break
            start += 100
        for a in acts:
            self.store.put("activity", a["activityId"], a)
        self.store.commit()
        new = [a for a in acts if not self.store.has("activity_detail", a["activityId"])]
        log.info("Actividades: %d en total, %d nuevas", len(acts), len(new))
        for i, a in enumerate(new, 1):
            aid = a["activityId"]
            self.store.put("activity_detail", aid, self.api.call("get_activity", aid))
            if i % 20 == 0:
                log.info("  detalle %d/%d", i, len(new))
                self.store.commit()
        self.store.commit()
        if self.fit:
            self._download_fits(acts)
        return acts

    def _download_fits(self, acts: list[dict]) -> None:
        FIT_DIR.mkdir(parents=True, exist_ok=True)
        missing = [a for a in acts if not (FIT_DIR / f"{a['activityId']}.fit").exists()
                   and not (FIT_DIR / f"{a['activityId']}.missing").exists()]
        log.info("Archivos FIT por descargar: %d", len(missing))
        for i, a in enumerate(missing, 1):
            aid = a["activityId"]
            try:
                blob = self.api.call("download_activity", aid)
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    fits = [n for n in z.namelist() if n.lower().endswith(".fit")]
                    if not fits:
                        (FIT_DIR / f"{aid}.missing").write_text("zip sin .fit")
                        continue
                    (FIT_DIR / f"{aid}.fit").write_bytes(z.read(fits[0]))
            except (HttpError, zipfile.BadZipFile) as e:
                log.warning("FIT %s no disponible: %s", aid, e)
                (FIT_DIR / f"{aid}.missing").write_text(str(e))
            if i % 25 == 0:
                log.info("  FIT %d/%d", i, len(missing))

    def sync_ranges(self, first: date) -> None:
        for ds in RANGE_DATASETS:
            done = self.store.state(f"done:{ds.name}")
            start = first if not done else date.fromisoformat(done) - timedelta(days=REFRESH_DAYS)
            start = max(start, first)
            total = 0
            for a, b in _days(start, self.today, ds.chunk_days):
                try:
                    total += self._fetch_range(ds, a, b)
                except HttpError as e:
                    log.warning("%s %s..%s: HTTP %s, lo salto", ds.name, a, b, e.status_code)
                self.store.commit()
            self.store.set_state(f"done:{ds.name}", self.today.isoformat())
            self.store.commit()
            log.info("%-14s %5d días guardados (%s → %s)", ds.name, total, start, self.today)

    def sync_intraday(self) -> None:
        """FC cada 2 minutos, un día por petición. Solo días con datos de reloj."""
        days = sorted(k for k, v in self.store.items("daily_summary") if v.get("includesWellnessData"))
        have = self.store.keys("heart_rate")
        recent = {(self.today - timedelta(days=i)).isoformat() for i in range(REFRESH_DAYS + 1)}
        todo = [d for d in days if d not in have or d in recent]
        log.info("FC intradía por descargar: %d días", len(todo))
        for i, d in enumerate(todo, 1):
            try:
                self.store.put("heart_rate", d, self.api.call("get_daily_heart_rate", d))
            except HttpError as e:
                log.warning("FC %s: HTTP %s", d, e.status_code)
            if i % 50 == 0:
                log.info("  FC %d/%d", i, len(todo))
                self.store.commit()
        self.store.commit()

    def run(self) -> None:
        self.sync_profile()
        acts = self.sync_activities()
        first = self.first_date(acts)
        self.sync_ranges(first)
        if self.intraday:
            self.sync_intraday()
        self.store.set_state("last_sync", self.today.isoformat())
        self.store.commit()
        log.info("Sincronización terminada: %d peticiones", self.api.calls)
