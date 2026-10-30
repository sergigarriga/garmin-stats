"""Descarga y análisis de datos de Garmin Connect con la Personal API oficial."""

import os
from pathlib import Path

# En AWS Lambda los datos viven en /tmp: se elige con GARMIN_STATS_ROOT.
ROOT = Path(os.environ.get("GARMIN_STATS_ROOT") or Path(__file__).resolve().parents[2])
DATA_DIR = ROOT / "data"
FIT_DIR = DATA_DIR / "fit"
DB_PATH = DATA_DIR / "garmin.sqlite"
REPORTS_DIR = ROOT / "reports"
SITE_DIR = ROOT / "site"
