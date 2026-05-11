"""Per-disease surveillance metrics from local `signals.db` (+ national snapshot context)."""
from __future__ import annotations

from typing import Any

import pandas as pd


def get_disease_surveillance_snapshot(disease: str, realtime_data: dict | None = None) -> dict[str, Any]:
    from .signal_store import count_disease_recent_hours, daily_aggregate

    d = (disease or "").strip() or "Unknown"
    c24 = count_disease_recent_hours(d, 24)
    c7d = count_disease_recent_hours(d, 24 * 7)
    daily = daily_aggregate(disease=d, days=120)

    anomaly: dict[str, Any] | None = None
    trend_label = "Insufficient history (need a few days in store)"
    if len(daily) >= 14:
        last = float(daily["count"].iloc[-1])
        hist = daily["count"].iloc[-15:-1].astype(float)
        mu = float(hist.mean())
        s = float(hist.std() or 0.01)
        z = (last - mu) / max(0.01, s)
        flag = "spike" if z > 2.0 else ("dip" if z < -2.0 else "within band")
        anomaly = {
            "z_score": round(z, 2),
            "last_day_count": int(last),
            "baseline_mean_14d_excl_last": round(mu, 2),
            "flag": flag,
        }
        a = float(daily["count"].iloc[-7:].sum())
        b = float(daily["count"].iloc[-14:-7].sum())
        if b <= 0:
            trend_label = "Rising (no prior-week baseline)" if a > 0 else "Quiet"
        elif a > b * 1.25:
            trend_label = "Rising vs prior week"
        elif a < b * 0.75:
            trend_label = "Falling vs prior week"
        else:
            trend_label = "Stable vs prior week"
    elif len(daily) >= 3:
        trend_label = "Short series — anomaly detection needs ~14 days"

    dash = (realtime_data or {}).get("dashboard") if isinstance(realtime_data, dict) else None
    if not isinstance(dash, dict):
        dash = {}

    return {
        "disease": d,
        "validated_count_24h": c24,
        "validated_count_7d": c7d,
        "daily": daily,
        "anomaly": anomaly,
        "trend_label": trend_label,
        "national_signal_score": dash.get("signal_score"),
        "national_risk_level": dash.get("risk_level"),
        "national_posture": dash.get("posture"),
    }
