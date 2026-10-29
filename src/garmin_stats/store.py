"""Almacén local: JSON crudo de la API en SQLite, una fila por (dataset, clave)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw (
    dataset    TEXT NOT NULL,
    key        TEXT NOT NULL,
    payload    TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (dataset, key)
);
CREATE TABLE IF NOT EXISTS sync_state (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def put(self, dataset: str, key: str, obj) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO raw VALUES (?, ?, ?, ?)",
            (dataset, str(key), json.dumps(obj), datetime.now(timezone.utc).isoformat()),
        )

    def has(self, dataset: str, key: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM raw WHERE dataset = ? AND key = ?", (dataset, str(key))
        )
        return cur.fetchone() is not None

    def keys(self, dataset: str) -> set[str]:
        cur = self.conn.execute("SELECT key FROM raw WHERE dataset = ?", (dataset,))
        return {r[0] for r in cur}

    def items(self, dataset: str) -> Iterator[tuple[str, object]]:
        cur = self.conn.execute(
            "SELECT key, payload FROM raw WHERE dataset = ? ORDER BY key", (dataset,)
        )
        for key, payload in cur:
            yield key, json.loads(payload)

    def get(self, dataset: str, key: str):
        cur = self.conn.execute(
            "SELECT payload FROM raw WHERE dataset = ? AND key = ?", (dataset, str(key))
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def state(self, name: str) -> str | None:
        row = self.conn.execute("SELECT value FROM sync_state WHERE name = ?", (name,)).fetchone()
        return row[0] if row else None

    def set_state(self, name: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO sync_state VALUES (?, ?)", (name, value))

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
