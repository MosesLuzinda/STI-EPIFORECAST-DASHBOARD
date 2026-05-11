"""
Coolio **signal lens**: reads validator-approved rows from ``signals.db``, classifies
them by source tier (official agency feeds vs open-web), and exposes recent
**official** events to the dashboard. This is the “filter” on top of data the
pipelines already ingested — not a replacement for ``signal_validator``.
"""
from __future__ import annotations

import os
from collections import Counter

from .coolio_sources import is_official_verified_source, source_tier
from .signal_store import fetch_recent_validated_signals


def coolio_signal_lens_enabled() -> bool:
    eng = (os.getenv("EPFORECAST_SIGNAL_FORECAST_ENGINE") or "").strip().lower()
    if eng in ("coolio", "coolio1"):
        return True
    return os.getenv("EPFORECAST_COOLIO_SIGNAL_LENS", "").strip().lower() in ("1", "true", "yes")


def enrich_realtime_with_coolio_signal_lens(realtime_data: dict) -> None:
    """
    Sets ``coolio_signal_lens`` (counts by tier) and ``coolio_verified_events``
    (recent official-feed items, newest first).
    """
    realtime_data.setdefault("coolio_signal_lens", {})
    realtime_data.setdefault("coolio_verified_events", [])

    if not coolio_signal_lens_enabled():
        realtime_data["coolio_signal_lens"] = {}
        realtime_data["coolio_verified_events"] = []
        return

    try:
        wh = int(os.getenv("EPFORECAST_COOLIO_LENS_HOURS", "72") or "72")
    except ValueError:
        wh = 72
    wh = max(6, min(168, wh))
    try:
        lim = int(os.getenv("EPFORECAST_COOLIO_LENS_LIMIT", "150") or "150")
    except ValueError:
        lim = 150
    lim = max(20, min(400, lim))

    rows = fetch_recent_validated_signals(hours=wh, limit=lim)
    tier_counts = Counter(source_tier(r.get("source")) for r in rows)
    official_rows = [r for r in rows if is_official_verified_source(r.get("source"))]

    events: list[dict] = []
    for r in official_rows[:30]:
        events.append(
            {
                "ts": r.get("ts") or "",
                "source": str(r.get("source") or ""),
                "disease": str(r.get("disease") or ""),
                "title": str(r.get("title") or "")[:220],
                "url": str(r.get("url") or "")[:600],
                "confidence": float(r.get("confidence") or 0.0),
                "engine": str(r.get("engine") or ""),
                "tier": "official",
            }
        )

    realtime_data["coolio_signal_lens"] = {
        "window_hours": wh,
        "validated_in_window": len(rows),
        "by_tier": dict(tier_counts),
        "official_count": len(official_rows),
    }
    realtime_data["coolio_verified_events"] = events
