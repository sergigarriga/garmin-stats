"""Lectura de archivos FIT: registros segundo a segundo + resumen de sesión."""

from __future__ import annotations

import logging
from pathlib import Path

import fitdecode
import pandas as pd

log = logging.getLogger(__name__)

RECORD_FIELDS = {
    "timestamp": "ts",
    "heart_rate": "hr",
    "enhanced_speed": "speed",
    "speed": "speed_raw",
    "cadence": "cadence",
    "fractional_cadence": "cadence_frac",
    "distance": "distance",
    "enhanced_altitude": "altitude",
    "power": "power",
}

SESSION_FIELDS = [
    "sport", "sub_sport", "total_timer_time", "total_distance", "avg_heart_rate",
    "max_heart_rate", "avg_step_length", "avg_vertical_oscillation", "avg_stance_time",
    "avg_vertical_ratio", "total_ascent", "avg_power", "normalized_power",
    "workout_rpe", "workout_feel", "avg_cadence",
]


def parse_fit(path: Path) -> tuple[dict, pd.DataFrame]:
    """Devuelve (resumen, registros). El VO2max sale del mensaje 140 (no documentado):
    campo 7 × 3,5 / 65536 = ml/kg/min, decodificación conocida en la comunidad."""
    summary: dict = {}
    rows: list[dict] = []
    with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.DISABLED) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            name = frame.name
            if name == "record":
                row = {}
                for f in frame.fields:
                    col = RECORD_FIELDS.get(f.name)
                    if col and f.value is not None:
                        row[col] = f.value
                if "ts" in row:
                    rows.append(row)
            elif name == "session" and "sport" not in summary:
                vals = {f.name: f.value for f in frame.fields}
                for k in SESSION_FIELDS:
                    v = vals.get(k)
                    summary[k] = v if not isinstance(v, (tuple, list)) else None
            elif name == "unknown_140":
                vals = {f.name: f.value for f in frame.fields}
                raw = vals.get("unknown_7")
                if isinstance(raw, int) and raw > 0:
                    vo2 = raw * 3.5 / 65536
                    if 15 < vo2 < 95:
                        summary["vo2max_fit"] = round(vo2, 1)
            elif name == "time_in_zone":
                vals = {f.name: f.value for f in frame.fields}
                if vals.get("reference_mesg") == "session" and vals.get("max_heart_rate"):
                    summary["fit_max_hr"] = vals.get("max_heart_rate")
                    summary["fit_rest_hr"] = vals.get("resting_heart_rate")
    df = pd.DataFrame(rows)
    if not df.empty:
        if "speed" not in df and "speed_raw" in df:
            df["speed"] = df["speed_raw"]
        elif "speed_raw" in df:
            df["speed"] = df["speed"].fillna(df["speed_raw"])
        if "cadence_frac" in df and "cadence" in df:
            df["cadence"] = df["cadence"] + df["cadence_frac"].fillna(0)
        df = df.drop(columns=[c for c in ("speed_raw", "cadence_frac") if c in df])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return summary, df
