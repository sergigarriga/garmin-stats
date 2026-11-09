"""Línea de comandos: garmin-stats sync | report | all."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import DB_PATH, REPORTS_DIR, SITE_DIR
from . import analysis as R
from . import export as X
from . import metrics as M
from . import tables as T
from .store import Store

log = logging.getLogger("garmin_stats")


def cmd_sync(args) -> None:
    from .api import Api
    from .sync import Syncer

    store = Store(DB_PATH)
    api = Api(pause=args.pause)
    try:
        Syncer(api, store, intraday=not args.no_intraday, fit=not args.no_fit).run()
    finally:
        api.close()
        store.close()


def cmd_report(args) -> None:
    store = Store(DB_PATH)
    try:
        n = T.parse_new_fits(store)
        from . import extras
        n_sets = extras.parse_new_strength(store)
        if n_sets:
            log.info("Series de fuerza leídas: %d sesiones", n_sets)
        sets = dict(store.items("strength_sets"))
        if n:
            log.info("FIT procesados: %d", n)
        prof = T.profile(store)
        tables = {"daily": T.daily(store), "sleep": T.sleep(store), "hrv": T.hrv(store),
                  "weight": T.weight(store), "activities": T.activities(store)}
        fs = T.fit_summary(store)
        acts = tables["activities"]
        if acts.empty and tables["daily"].empty:
            sys.exit("No hay datos. Ejecuta antes: garmin-stats sync")
        fit_hr_max = fs["fit_max_hr"].dropna().iloc[-1] if "fit_max_hr" in fs and fs["fit_max_hr"].notna().any() else None
        max_hr = prof.get("max_hr") or fit_hr_max or 190
        rest_hr = prof.get("rest_hr") or 60
        rec = T.fit_records(store, acts["activity_id"]) if not acts.empty else None
        am = M.activity_metrics(acts, fs, rec if rec is not None else T.pd.DataFrame(), rest_hr, max_hr)
        A = R.assemble({**tables, "activities": am}, prof)
        T.write_tables(store, {**tables, "activity_metrics": am, "load": A["load"],
                               "day": A["day"].reset_index()})
        data = X.payload(A, am, store.state("last_sync"), sets)
        from . import extras, training
        data["live"] = X._safe("live", lambda: extras.live(store), None)
        from . import weather
        try:
            weather.refresh()  # previsión de tu ciudad (como mucho cada ~3 h; si falla, sin previsión)
            data["lastRunArea"] = weather.last_run_area(store)
        except Exception as e:  # noqa: BLE001 - el informe no se cae por el tiempo
            log.warning("Previsión del tiempo: %s", e)
        X._safe("training", lambda: training.enrich(data), None)
        n_det = X._safe("activity_details", lambda: extras.write_activity_details(am, SITE_DIR, prof.get("zones")), 0)
        if n_det:
            log.info("Detalle de actividades: %d archivos", n_det)
        from . import ai
        data["ai"] = ai.generate(data, force=args.force_ai, offline=args.no_ai)
        data["weekly"] = ai.weekly(data, offline=args.no_ai)
        from . import coach
        if not args.no_ai:
            try:
                coach.adapt(data=data)  # solo hace algo el primer informe de cada semana
            except Exception as e:  # el informe no debe caerse por el coach
                log.warning("Coach: no se pudo reajustar el plan (%s)", e)
        data["coach"] = X._safe("coach_view", lambda: coach.view(data), None)
        from . import odds
        data["goalOdds"] = X._safe("goal_odds", lambda: odds.with_history(
            odds.compute((data.get("coach") or {}).get("plan"), data.get("paces")), store), None)
        if os.environ.get("GARMIN_STATS_OWNER") == "1":  # solo la dueña ve los costes de IA; el tope sigue activo
            data["aiUsage"] = ai.usage()
        else:
            _strip_costs(data.get("coach"))
        log.info("Web: %s", X.write_site(data, SITE_DIR))
        log.info("Resumen: %s", X.write_markdown(data, REPORTS_DIR))
    finally:
        store.close()



def _strip_costs(node) -> None:
    """Quita los campos de coste (€/$ de IA) de un bloque de datos, en cualquier nivel."""
    if isinstance(node, dict):
        for k in [k for k in node if k in ("cost", "costUsd")]:
            node.pop(k)
        for v in node.values():
            _strip_costs(v)
    elif isinstance(node, list):
        for v in node:
            _strip_costs(v)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="garmin-stats", description="Datos Garmin → SQLite → informe")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="Descarga de Garmin (completo la 1.ª vez, incremental después)")
    s.add_argument("--no-intraday", action="store_true", help="No bajar la FC cada 2 min por día")
    s.add_argument("--no-fit", action="store_true", help="No bajar los archivos FIT")
    s.add_argument("--pause", type=float, default=0.35, help="Segundos entre peticiones")
    r = sub.add_parser("report", help="Calcula el análisis y actualiza la web (site/) y el resumen Markdown")
    a = sub.add_parser("all", help="sync + report")
    a.add_argument("--no-intraday", action="store_true")
    a.add_argument("--no-fit", action="store_true")
    a.add_argument("--pause", type=float, default=0.35)
    for x in (r, a):
        x.add_argument("--no-ai", action="store_true", help="No llamar a Claude (usa los últimos textos guardados)")
        x.add_argument("--force-ai", action="store_true", help="Regenerar los textos de IA aunque no haya datos nuevos")
    sv = sub.add_parser("serve", help="Sirve la web en http://localhost:8765 con el chat de IA")
    sv.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if not args.verbose:
        logging.getLogger("garmin_personal_api").setLevel(logging.WARNING)
    if args.cmd in ("sync", "all"):
        cmd_sync(args)
    if args.cmd in ("report", "all"):
        cmd_report(args)
    if args.cmd == "serve":
        from .server import serve
        serve(args.port)


if __name__ == "__main__":
    main()
