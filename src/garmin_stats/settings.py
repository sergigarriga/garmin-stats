"""Ajustes del usuario en data/settings.json (por ejemplo, periodos con el reloj roto)."""

from __future__ import annotations

import json
from datetime import date, timedelta

from . import DATA_DIR

PATH = DATA_DIR / "settings.json"


def load() -> dict:
    try:
        return json.loads(PATH.read_text())
    except (OSError, ValueError):
        return {}


def watch_gaps() -> list[dict]:
    return load().get("watch_gaps", [])


def in_gap(d: date) -> bool:
    return any(date.fromisoformat(g["from"]) <= d <= date.fromisoformat(g["to"]) for g in watch_gaps())


def recorded_start(days: int, today: date | None = None) -> date:
    """Fecha desde la que hay `days` días REGISTRADOS hasta hoy, saltando los huecos del reloj."""
    cur = today or date.today()
    left = days
    while left > 0:
        cur -= timedelta(days=1)
        if not in_gap(cur):
            left -= 1
    return cur
