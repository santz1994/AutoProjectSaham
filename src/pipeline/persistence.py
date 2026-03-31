"""Persistence helpers for ETL outputs.

Provides a tiny SQLite-backed helper to store ETL run results so the
autonomous pipeline can persist outputs for auditing and downstream
consumers.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional


def _ensure_db(db_path: str) -> None:
    d = os.path.dirname(db_path) or '.'
    os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        '''CREATE TABLE IF NOT EXISTS etl_runs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               ts INTEGER NOT NULL,
               symbols_count INTEGER,
               etl_json TEXT,
               prices_json TEXT
           )'''
    )
    conn.commit()
    conn.close()


def save_etl_run(
    etl_result: Dict[str, Any],
    prices_report: Optional[List[Dict[str, Any]]] = None,
    db_path: str = 'data/etl.db',
) -> int:
    """Save a single ETL run result to `db_path` and return the inserted row id.

    The function creates the DB/tables if missing and stores JSON payloads
    for inspection and audit.
    """
    _ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ts = int(time.time())
    # best-effort symbol count from etl_result
    symbol_count = 0
    try:
        stocks = etl_result.get('stocks')
        if isinstance(stocks, dict):
            symbol_count = len(stocks)
        elif isinstance(stocks, list):
            symbol_count = len(stocks)
    except Exception:
        symbol_count = 0

    cur.execute(
        'INSERT INTO etl_runs(ts, symbols_count, etl_json, prices_json) VALUES (?,?,?,?)',
        (ts, symbol_count, json.dumps(etl_result), json.dumps(prices_report)),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return int(rowid)


def read_etl_runs(
    limit: int = 10,
    db_path: str = 'data/etl.db',
) -> List[Dict[str, Any]]:
    _ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        'SELECT id, ts, symbols_count, etl_json, prices_json FROM etl_runs '
        'ORDER BY ts DESC LIMIT ?',
        (limit,),
    )
    rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for id_, ts, symbols_count, etl_json, prices_json in rows:
        out.append({
            'id': id_,
            'ts': ts,
            'symbols_count': symbols_count,
            'etl': json.loads(etl_json) if etl_json else None,
            'prices': json.loads(prices_json) if prices_json else None,
        })
    conn.close()
    return out
