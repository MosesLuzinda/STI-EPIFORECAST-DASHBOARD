"""
SQLite-backed store of validated outbreak signals.

Every accepted feed item (after the AI validator approves it) is appended
here so the signal-trained forecast model can train on multi-day history
instead of a single 24h snapshot. Default file: `data/signals.db` under the
repository root (see `backend/project_paths.PROJECT_ROOT`).

Schema (table `signals`):
    id          INTEGER PRIMARY KEY
    ts          TEXT  (ISO-8601 UTC)
    source      TEXT
    title       TEXT
    url         TEXT  (UNIQUE - acts as a dedupe key across refreshes)
    disease     TEXT
    location    TEXT
    confidence  REAL
    engine      TEXT  ("llm" | "keyword" | "cache")
    reason      TEXT

Public API:
    init_db()
    append_signals(rows)         -> int (rows inserted)
    count_recent(hours)          -> int
    list_diseases(min_count)     -> list[str]
    disease_counts_recent(hours, min_count) -> list[tuple[str, int]]
    load_signal_history(days)    -> DataFrame
    daily_aggregate(disease, days) -> DataFrame[date, count]
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .project_paths import PROJECT_ROOT


def _resolved_db_path() -> Path:
    raw = (os.getenv("SIGNAL_DB_PATH") or "data/signals.db").strip()
    p = Path(raw)
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


DB_PATH = _resolved_db_path()

_init_lock = threading.Lock()
_initialized = False


def _ensure_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _conn():
    _ensure_dir()
    con = sqlite3.connect(str(DB_PATH))
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        with _conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    disease TEXT,
                    location TEXT,
                    confidence REAL,
                    engine TEXT,
                    reason TEXT
                )
                """
            )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_url "
                "ON signals(url) WHERE url IS NOT NULL"
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_signals_disease ON signals(disease)")
        _initialized = True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_signals(rows: list[dict]) -> int:
    """Insert validated signals; UNIQUE(url) silently dedupes across refreshes."""
    if not rows:
        return 0
    init_db()
    inserted = 0
    with _conn() as con:
        for row in rows:
            try:
                before = con.total_changes
                con.execute(
                    """
                    INSERT OR IGNORE INTO signals
                        (ts, source, title, url, disease, location,
                         confidence, engine, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("ts") or _utc_now_iso(),
                        str(row.get("source") or "")[:60],
                        str(row.get("title") or "")[:400],
                        (str(row.get("url") or "")[:600] or None),
                        (str(row.get("disease") or "")[:60] or None),
                        (str(row.get("location") or "")[:120] or None),
                        float(row.get("confidence") or 0.0),
                        (str(row.get("engine") or "")[:20] or None),
                        (str(row.get("reason") or "")[:240] or None),
                    ),
                )
                inserted += con.total_changes - before
            except Exception:
                continue
    return int(inserted)


def count_recent(hours: int = 24) -> int:
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).replace(microsecond=0).isoformat()
    with _conn() as con:
        cur = con.execute("SELECT COUNT(*) FROM signals WHERE ts >= ?", (cutoff,))
        return int(cur.fetchone()[0])


def list_diseases(min_count: int = 5) -> list[str]:
    init_db()
    with _conn() as con:
        cur = con.execute(
            """
            SELECT disease, COUNT(*) AS n
            FROM signals
            WHERE disease IS NOT NULL AND disease <> ''
            GROUP BY disease
            HAVING n >= ?
            ORDER BY n DESC
            """,
            (int(min_count),),
        )
        return [str(r[0]) for r in cur.fetchall()]


def disease_counts_recent(hours: int = 24, min_count: int = 1) -> list[tuple[str, int]]:
    """Per-disease counts of validated signals in the rolling window (UTC)."""
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).replace(microsecond=0).isoformat()
    with _conn() as con:
        cur = con.execute(
            """
            SELECT disease, COUNT(*) AS n
            FROM signals
            WHERE ts >= ?
              AND disease IS NOT NULL
              AND TRIM(disease) <> ''
            GROUP BY disease
            HAVING n >= ?
            ORDER BY n DESC
            """,
            (cutoff, int(min_count)),
        )
        return [(str(r[0]), int(r[1])) for r in cur.fetchall()]


def count_disease_recent_hours(disease: str, hours: int = 24) -> int:
    """Count validated signals for one disease label in a rolling UTC window."""
    label = str(disease or "").strip()
    if not label:
        return 0
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).replace(microsecond=0).isoformat()
    with _conn() as con:
        cur = con.execute(
            """
            SELECT COUNT(*) FROM signals
            WHERE ts >= ? AND LOWER(TRIM(disease)) = LOWER(TRIM(?))
            """,
            (cutoff, label),
        )
        return int(cur.fetchone()[0])


def fetch_recent_validated_signals(hours: int = 72, limit: int = 120) -> list[dict]:
    """Recent validator-approved rows (newest first). Used by Coolio dashboard lens."""
    init_db()
    h = max(1, int(hours))
    lim = max(1, min(500, int(limit)))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=h)).replace(microsecond=0).isoformat()
    with _conn() as con:
        cur = con.execute(
            """
            SELECT ts, source, title, url, disease, location, confidence, engine
            FROM signals
            WHERE ts >= ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (cutoff, lim),
        )
        cols = ["ts", "source", "title", "url", "disease", "location", "confidence", "engine"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def load_signal_history(days: int = 90) -> pd.DataFrame:
    """Return validated signals within the lookback window as a DataFrame."""
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).replace(microsecond=0).isoformat()
    with _conn() as con:
        df = pd.read_sql_query(
            """
            SELECT ts, source, disease, location, confidence, title, url, engine
            FROM signals
            WHERE ts >= ?
            ORDER BY ts ASC
            """,
            con,
            params=(cutoff,),
        )
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    df = df.dropna(subset=["ts"]).reset_index(drop=True)
    df["date"] = df["ts"].dt.tz_convert("UTC").dt.date
    return df


def daily_aggregate(
    disease: str | None = None,
    days: int = 90,
    *,
    source_tier_filter: frozenset[str] | None = None,
) -> pd.DataFrame:
    """
    Daily counts (optionally filtered by disease) ready for time-series modelling.

    ``source_tier_filter`` when set (e.g. ``frozenset({"official"})``) keeps only
    rows whose ``source`` label maps to that tier; see ``coolio_sources.source_tier``.
    """
    from .coolio_sources import source_tier

    df = load_signal_history(days=days)
    if df.empty:
        return pd.DataFrame(columns=["date", "count"])
    if source_tier_filter:
        df = df[df["source"].map(lambda s: source_tier(str(s)) in source_tier_filter)]
    if df.empty:
        return pd.DataFrame(columns=["date", "count"])
    if disease:
        df = df[df["disease"].astype(str).str.lower() == disease.lower()]
    if df.empty:
        return pd.DataFrame(columns=["date", "count"])
    daily = df.groupby("date").size().reset_index(name="count")
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values("date").reset_index(drop=True)
