"""
When Coolio is enabled (forecast engine or EPFORECAST_COOLIO_AUTO_INGEST), pull a live
OWID snapshot into each outbreak dashboard fetch so KPIs can reflect COVID context
without waiting on the 24h training cache alone.
"""
from __future__ import annotations

import os

from .coolio_owid import get_owid_live_snapshot
from .statistical_forecast import offline_snapshot_mode


def coolio_live_ingest_enabled() -> bool:
    eng = (os.getenv("EPFORECAST_SIGNAL_FORECAST_ENGINE") or "").strip().lower()
    if eng in ("coolio", "coolio1"):
        return True
    flag = (os.getenv("EPFORECAST_COOLIO_AUTO_INGEST") or "").strip().lower()
    return flag in ("1", "true", "yes")


def coolio_owid_iso() -> str:
    raw = (os.getenv("EPFORECAST_COOLIO_OWID_ISO") or "UGA").strip().upper()
    return raw or "UGA"


def enrich_realtime_for_coolio_live(realtime_data: dict) -> None:
    """Set coolio_live (snapshot dict) and coolio_signal_nudge (0–cap) on realtime_data."""
    if offline_snapshot_mode():
        realtime_data.setdefault("coolio_live", None)
        realtime_data.setdefault("coolio_signal_nudge", 0.0)
        return
    if not coolio_live_ingest_enabled():
        realtime_data["coolio_live"] = None
        realtime_data["coolio_signal_nudge"] = 0.0
        return
    snap = get_owid_live_snapshot(iso_code=coolio_owid_iso())
    realtime_data["coolio_live"] = snap
    nudge = 0.0
    if snap.get("ok"):
        cases = float(snap.get("new_cases_smoothed") or 0.0)
        nudge = min(4.0, (cases / 350.0) * 3.5)
    realtime_data["coolio_signal_nudge"] = float(nudge)
