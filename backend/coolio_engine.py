"""
Coolio — stacked signal forecast: Random Forest + Histogram Gradient Boosting.

Trains on the same validated `signals.db` daily counts as the legacy RF forecaster,
optionally augments COVID-style runs with **Our World in Data** (public CSV, cached).

Enable with: EPFORECAST_SIGNAL_FORECAST_ENGINE=coolio

**World mode:** set ``EPFORECAST_COOLIO_ML=0`` to skip sklearn entirely and use
``coolio_world_briefing`` (Wikipedia + WHO RSS + OWID for COVID + optional LLM).
When local history is missing, ``EPFORECAST_COOLIO_WORLD_FALLBACK=1`` (default)
calls that briefing instead of an empty error.

A separate **LLM reasoning layer** (same providers as the rest of the app) adds analyst-style
briefings when ``EPFORECAST_COOLIO_LLM`` is on and credentials exist — see ``coolio_llm``.
"""
from __future__ import annotations

import os
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

from .coolio_llm import enrich_coolio_forecast_with_llm
from .coolio_owid import disease_uses_owid_covid, merge_owid_into_daily
from .signal_store import daily_aggregate as _signal_daily_aggregate

MIN_HISTORY_DAYS = 14
LAGS = (1, 2, 3, 7, 14)
ROLL_WINDOWS = (3, 7)
COOLIO_VERSION = "1.0.0"


def _coolio_ml_enabled() -> bool:
    return (os.getenv("EPFORECAST_COOLIO_ML", "1") or "1").strip().lower() not in ("0", "false", "no")


def _world_fallback_enabled() -> bool:
    return (os.getenv("EPFORECAST_COOLIO_WORLD_FALLBACK", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _forecast_source_tier_filter():
    """Optional: train only on official-tier rows (sparse); see ``coolio_sources``."""
    raw = (os.getenv("EPFORECAST_COOLIO_FORECAST_SOURCE_TIER") or "").strip().lower()
    if raw in ("official", "agency", "verified_publishers"):
        return frozenset({"official"})
    if raw in ("official_open_web", "standard"):
        return frozenset({"official", "open_web"})
    return None


def _prepare_frame(daily: pd.DataFrame, disease: str | None) -> tuple[pd.DataFrame | None, list[str]]:
    daily = daily.set_index("date").asfreq("D", fill_value=0).reset_index()
    daily = daily.rename(columns={"index": "date"})
    daily = merge_owid_into_daily(daily, disease)

    df = daily.copy()
    for lag in LAGS:
        df[f"lag_{lag}"] = df["count"].shift(lag)
    for w in ROLL_WINDOWS:
        df[f"roll_{w}"] = df["count"].shift(1).rolling(w).mean()
    df["dow"] = pd.to_datetime(df["date"]).dt.dayofweek
    df = df.dropna().reset_index(drop=True)
    if df.empty:
        return None, []
    feature_cols = [c for c in df.columns if c not in ("date", "count")]
    return df, feature_cols


def run_coolio_signal_forecast(
    disease: str | None = None,
    horizon_days: int = 14,
    lookback_days: int = 120,
) -> dict:
    from .coolio_world_briefing import run_coolio_world_briefing
    from .data_services import _run_naive_signal_forecast

    base_payload: dict = {
        "ok": False,
        "reason": "",
        "history": pd.DataFrame(columns=["date", "count"]),
        "forecast": pd.DataFrame(columns=["date", "predicted", "lower", "upper"]),
        "feature_importance": [],
        "backtest": {},
        "disease": disease or "All",
        "horizon_days": int(horizon_days),
        "lookback_days": int(lookback_days),
        "min_history_days": MIN_HISTORY_DAYS,
        "rows_available": 0,
        "forecast_method": "coolio",
        "forecast_note": "",
    }

    daily = _signal_daily_aggregate(
        disease=disease,
        days=int(lookback_days),
        source_tier_filter=_forecast_source_tier_filter(),
    )
    rows_available = int(len(daily))

    if not _coolio_ml_enabled():
        return run_coolio_world_briefing(
            disease=disease,
            horizon_days=int(horizon_days),
            lookback_days=int(lookback_days),
            local_daily=daily,
        )

    base_payload["rows_available"] = rows_available
    base_payload["history"] = daily

    if daily.empty:
        if _world_fallback_enabled():
            return run_coolio_world_briefing(
                disease=disease,
                horizon_days=int(horizon_days),
                lookback_days=int(lookback_days),
                local_daily=daily,
            )
        base_payload["reason"] = "No validated signal days in the selected lookback window."
        return base_payload

    if rows_available < MIN_HISTORY_DAYS:
        if rows_available >= 3:
            naive = _run_naive_signal_forecast(
                disease=disease,
                horizon_days=int(horizon_days),
                lookback_days=int(lookback_days),
                daily_sparse=daily,
                min_rf_days=MIN_HISTORY_DAYS,
            )
            naive["forecast_method"] = "coolio_naive_fallback"
            fn = (naive.get("forecast_note") or "").strip()
            naive["forecast_note"] = (
                (fn + " ") if fn else ""
            ) + "Coolio: damped trend until enough history for the ensemble."
            return enrich_coolio_forecast_with_llm(naive)
        if _world_fallback_enabled():
            return run_coolio_world_briefing(
                disease=disease,
                horizon_days=int(horizon_days),
                lookback_days=int(lookback_days),
                local_daily=daily,
            )
        base_payload["reason"] = (
            f"Not enough validated signal history yet ({rows_available} day(s); "
            f"need 3 for naive or {MIN_HISTORY_DAYS} for Coolio ensemble)."
        )
        return base_payload

    frame, feature_cols = _prepare_frame(daily, disease)
    if frame is None or not feature_cols:
        base_payload["reason"] = "Not enough contiguous signal history to build lag features yet."
        return base_payload

    X = frame[feature_cols].values
    y = frame["count"].astype(float).values

    split = max(1, int(len(frame) * 0.8))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    mae_rf = 1.0
    mae_hgb = 1.0
    if len(X_test) > 0:
        bt_rf = RandomForestRegressor(n_estimators=300, random_state=42)
        bt_hgb = HistGradientBoostingRegressor(
            max_iter=200,
            learning_rate=0.07,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.12,
            n_iter_no_change=12,
        )
        bt_rf.fit(X_train, y_train)
        bt_hgb.fit(X_train, y_train)
        p_rf = bt_rf.predict(X_test)
        p_hgb = bt_hgb.predict(X_test)
        mae_rf = float(np.mean(np.abs(p_rf - y_test)))
        mae_hgb = float(np.mean(np.abs(p_hgb - y_test)))
        blend_p = 0.5 * p_rf + 0.5 * p_hgb
        denom = np.where(y_test == 0, 1.0, y_test)
        mape = float(np.mean(np.abs((blend_p - y_test) / denom)))
        mae = float(np.mean(np.abs(blend_p - y_test)))
        backtest: dict = {
            "mae": round(mae, 2),
            "mape": round(mape, 4),
            "n": int(len(X_test)),
            "mae_rf": round(mae_rf, 3),
            "mae_hgb": round(mae_hgb, 3),
        }
    else:
        backtest = {"mae": None, "mape": None, "n": 0}

    eps = 1e-6
    w_rf = 1.0 / (mae_rf + eps)
    w_hgb = 1.0 / (mae_hgb + eps)
    s = w_rf + w_hgb
    w_rf /= s
    w_hgb /= s

    model_rf = RandomForestRegressor(n_estimators=400, random_state=42)
    model_hgb = HistGradientBoostingRegressor(
        max_iter=280,
        learning_rate=0.06,
        random_state=42,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=15,
    )
    model_rf.fit(X, y)
    model_hgb.fit(X, y)

    imp_rf = model_rf.feature_importances_
    imp_hgb = model_hgb.feature_importances_
    imp_sum = imp_rf.sum() + 1e-9
    imp_sum2 = imp_hgb.sum() + 1e-9
    blend_imp = 0.5 * (imp_rf / imp_sum + imp_hgb / imp_sum2)
    importance = sorted(
        [
            {"feature": feat, "importance": round(float(imp), 4)}
            for feat, imp in zip(feature_cols, blend_imp)
        ],
        key=lambda r: r["importance"],
        reverse=True,
    )

    daily_ff = daily.set_index("date").asfreq("D", fill_value=0).reset_index()
    daily_ff = daily_ff.rename(columns={"index": "date"})
    daily_ff = merge_owid_into_daily(daily_ff, disease)
    last_date = pd.to_datetime(daily_ff["date"].iloc[-1])
    series = daily_ff["count"].astype(float).tolist()

    forecast_rows: list[dict] = []
    for step in range(int(horizon_days)):
        future_date = last_date + timedelta(days=step + 1)
        feat: dict[str, float] = {}
        for lag in LAGS:
            feat[f"lag_{lag}"] = float(series[-lag] if len(series) >= lag else 0.0)
        for w in ROLL_WINDOWS:
            window = series[-w:] if len(series) >= w else series
            feat[f"roll_{w}"] = float(sum(window) / max(1, len(window)))
        feat["dow"] = float(future_date.dayofweek)
        if disease_uses_owid_covid(disease):
            last_hist = daily_ff.iloc[-1]
            for ext_c in feature_cols:
                if ext_c.startswith("owid_"):
                    feat[ext_c] = float(last_hist.get(ext_c, 0) or 0)

        x_row = np.array([[feat[c] for c in feature_cols]])
        trees = np.array([est.predict(x_row)[0] for est in model_rf.estimators_])
        pred_rf = float(max(0.0, trees.mean()))
        pred_hgb = float(max(0.0, model_hgb.predict(x_row)[0]))
        pred = float(max(0.0, w_rf * pred_rf + w_hgb * pred_hgb))
        spread = float(np.std(trees)) if len(trees) > 1 else max(pred * 0.15, 0.5)
        lower = float(max(0.0, pred - 1.15 * spread))
        upper = float(max(lower + 0.01, pred + 1.15 * spread))

        forecast_rows.append(
            {
                "date": future_date.normalize(),
                "predicted": round(pred, 2),
                "lower": round(lower, 2),
                "upper": round(upper, 2),
            }
        )
        series.append(pred)

    forecast_df = pd.DataFrame(forecast_rows)
    if not forecast_df.empty:
        forecast_df["date"] = pd.to_datetime(forecast_df["date"])

    owid_bit = ""
    if disease_uses_owid_covid(disease):
        owid_bit = " OWID COVID public time series (Uganda) merged when available."

    note = (
        f"Coolio v{COOLIO_VERSION}: RF+HGB ensemble (weights RF={w_rf:.2f}, HGB={w_hgb:.2f} from hold-out MAE).{owid_bit}"
    )

    return enrich_coolio_forecast_with_llm(
        {
            "ok": True,
            "reason": "",
            "history": daily_ff,
            "forecast": forecast_df,
            "feature_importance": importance,
            "backtest": backtest,
            "disease": disease or "All",
            "horizon_days": int(horizon_days),
            "lookback_days": int(lookback_days),
            "min_history_days": MIN_HISTORY_DAYS,
            "rows_available": rows_available,
            "forecast_method": "coolio",
            "forecast_note": note,
        }
    )
