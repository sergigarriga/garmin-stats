"""Descarga y análisis de datos de Garmin Connect con la Personal API oficial."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FIT_DIR = DATA_DIR / "fit"
DB_PATH = DATA_DIR / "garmin.sqlite"
REPORTS_DIR = ROOT / "reports"
SITE_DIR = ROOT / "site"
