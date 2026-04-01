"""Simple persistence helpers for tick storage using SQLite.

This module keeps the dependency surface minimal (uses stdlib sqlite3)
and provides small conveniences for inserting ticks and exporting a
DataFrame when `pandas` is available.
"""
from __future__ import annotations

import os
import sqlite3
import json
from typing import List, Dict, Optional


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def ensure_db(db_path: str = "data/ticks.db") -> None:
    _ensure_dir(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                size INTEGER,
                side TEXT,
                raw TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_tick(
    db_path: str,
    symbol: str,
    ts: int,
    price: float,
    size: int = 0,
    side: str = "",
    raw: Optional[Dict] = None,
) -> None:
    _ensure_dir(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ticks (ts, symbol, price, size, side, raw) VALUES (?, ?, ?, ?, ?, ?)",
            (int(ts), symbol, float(price), int(size or 0), side or "", json.dumps(raw or {})),
        )
        conn.commit()
    finally:
        conn.close()


def query_ticks(db_path: str, limit: Optional[int] = None) -> List[Dict]:
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        sql = "SELECT ts, symbol, price, size, side, raw FROM ticks ORDER BY ts"
        if limit:
            sql = sql + f" LIMIT {int(limit)}"
        cur.execute(sql)
        rows = cur.fetchall()
        out = []
        for ts, symbol, price, size, side, raw in rows:
            try:
                raw_parsed = json.loads(raw) if raw else {}
            except Exception:
                raw_parsed = {}
            out.append({"ts": int(ts), "symbol": symbol, "price": float(price), "size": int(size or 0), "side": side or "", "raw": raw_parsed})
        return out
    finally:
        conn.close()


def query_ticks_to_df(db_path: str):
    """Return a pandas.DataFrame if pandas is available, else None."""
    try:
        import pandas as pd
    except Exception:
        return None

    if not os.path.exists(db_path):
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query("SELECT ts, symbol, price, size, side FROM ticks ORDER BY ts", conn)
        return df
    finally:
        conn.close()


def export_ticks_csv(db_path: str, out_path: str = "data/ticks.csv", limit: Optional[int] = None) -> str:
    _ensure_dir(out_path)
    rows = query_ticks(db_path, limit=limit)
    import csv

    with open(out_path, "w", newline="") as fh:
        if not rows:
            fh.write("")
            return out_path
        writer = csv.DictWriter(fh, fieldnames=["ts", "symbol", "price", "size", "side"])
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in ("ts", "symbol", "price", "size", "side")})
    return out_path
