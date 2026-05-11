"""
Optional internet-sourced context for Coolio (public Our World in Data COVID-19 CSV).

Used only when the forecast disease looks like COVID-19. Cached on disk to avoid
hammering OWID; failures are non-fatal (returns empty frame).
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from io import BytesIO

import pandas as pd
import requests

from .project_paths import PROJECT_ROOT

OWID_COVID_CSV = "https://covid.ourworldindata.org/data/owid-covid-data.csv"
CACHE_DIR = PROJECT_ROOT / "data" / "coolio_cache"
# Max staleness of the on-disk OWID CSV before re-downloading (default: refresh often ~ live).
_LIVE_TTL_DEFAULT = 120


def _owid_disk_cache_ttl_sec() -> int:
    try:
        return max(30, int(os.getenv("EPFORECAST_COOLIO_LIVE_TTL_SEC", str(_LIVE_TTL_DEFAULT))))
    except ValueError:
        return _LIVE_TTL_DEFAULT


COVID_ALIASES = frozenset(
    {
        "covid-19",
        "covid19",
        "covid 19",
        "sars-cov-2",
        "sarscov2",
        "2019-ncov",
        "novel coronavirus",
    }
)


def _cache_path(url: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return CACHE_DIR / f"owid_{h}.csv"


def fetch_owid_covid_series(*, iso_code: str = "UGA") -> pd.DataFrame:
    """
    Return columns: date, owid_new_cases_smoothed, owid_stringency, owid_total_boosters_per_hundred.
    Empty DataFrame on any failure.
    """
    path = _cache_path(OWID_COVID_CSV)
    ttl = _owid_disk_cache_ttl_sec()
    try:
        if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
            raw = path.read_bytes()
        else:
            r = requests.get(OWID_COVID_CSV, timeout=45)
            r.raise_for_status()
            raw = r.content
            path.write_bytes(raw)
        df = pd.read_csv(BytesIO(raw))
    except Exception:
        return pd.DataFrame()

    if "iso_code" not in df.columns or "date" not in df.columns:
        return pd.DataFrame()

    sub = df[df["iso_code"].astype(str).str.upper() == iso_code.upper()].copy()
    if sub.empty:
        return pd.DataFrame()

    sub["date"] = pd.to_datetime(sub["date"]).dt.normalize()
    out = sub[["date"]].copy()
    for col, target in [
        ("new_cases_smoothed", "owid_new_cases_smoothed"),
        ("stringency_index", "owid_stringency"),
        ("total_boosters_per_hundred", "owid_total_boosters_per_hundred"),
    ]:
        if col in sub.columns:
            out[target] = pd.to_numeric(sub[col], errors="coerce").fillna(0.0)
        else:
            out[target] = 0.0
    return out.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def get_owid_live_snapshot(*, iso_code: str = "UGA") -> dict:
    """Latest OWID row for iso_code (public CSV); used for dashboard context."""
    series = fetch_owid_covid_series(iso_code=iso_code)
    if series.empty:
        return {"ok": False, "iso": iso_code.upper(), "error": "no_data", "source": "owid"}
    last = series.iloc[-1]
    dt = last["date"]
    if hasattr(dt, "strftime"):
        last_date = dt.strftime("%Y-%m-%d")
    else:
        last_date = str(dt)[:10]
    return {
        "ok": True,
        "iso": iso_code.upper(),
        "last_date": last_date,
        "new_cases_smoothed": float(last.get("owid_new_cases_smoothed", 0) or 0),
        "stringency_index": float(last.get("owid_stringency", 0) or 0),
        "total_boosters_per_hundred": float(last.get("owid_total_boosters_per_hundred", 0) or 0),
        "source": "ourworldindata.org",
        "source_url": OWID_COVID_CSV,
    }


def disease_uses_owid_covid(disease: str | None) -> bool:
    d = (disease or "").strip().casefold()
    return d in COVID_ALIASES or "covid" in d


def merge_owid_into_daily(daily: pd.DataFrame, disease: str | None) -> pd.DataFrame:
    """Left-join OWID columns onto daily signal counts when COVID-focused."""
    if daily.empty or not disease_uses_owid_covid(disease):
        return daily
    owid = fetch_owid_covid_series()
    if owid.empty:
        return daily
    m = daily.merge(owid, on="date", how="left")
    for c in (
        "owid_new_cases_smoothed",
        "owid_stringency",
        "owid_total_boosters_per_hundred",
    ):
        if c in m.columns:
            m[c] = m[c].fillna(0.0)
    return m
