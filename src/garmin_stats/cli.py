"""Línea de comandos: garmin-stats sync | report | all."""

from __future__ import annotations

import argparse
import logging
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
        data = X.payload(A, am, store.state("last_sync"))
        from . import extras
        n_det = extras.write_activity_details(am, SITE_DIR, prof.get("zones"))
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
        data["coach"] = coach.view(data)
        data["aiUsage"] = ai.usage()
        log.info("Web: %s", X.write_site(data, SITE_DIR))
        log.info("Resumen: %s", X.write_markdown(data, REPORTS_DIR))
    finally:
        store.close()


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
