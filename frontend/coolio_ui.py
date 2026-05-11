"""Coolio visual identity helpers and a 3D **live signal skyline** for the home hero."""
from __future__ import annotations

import html as html_lib

import numpy as np
import plotly.graph_objects as go

COOLIO_COLORSCALE = [
    [0.0, "#0b1224"],
    [0.30, "#134e4a"],
    [0.55, "#15803d"],
    [0.78, "#0ea5e9"],
    [1.0, "#e0f2fe"],
]


def _coolio_scene(height: int) -> dict:
    return dict(
        margin=dict(l=0, r=0, t=0, b=0),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        scene=dict(
            aspectmode="manual",
            aspectratio=dict(x=1.35, y=1.0, z=0.55),
            bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(
                visible=False,
                showbackground=False,
            ),
            camera=dict(eye=dict(x=1.65, y=-1.55, z=0.78)),
        ),
    )


def _empty_state_figure(height: int, message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        x=0.5, y=0.5, xref="paper", yref="paper",
        text=message, showarrow=False,
        font=dict(size=13, color="#475569"),
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def disease_signal_skyline_figure(
    realtime_data: dict | None,
    *,
    height: int = 320,
    max_diseases: int = 8,
) -> go.Figure:
    """
    3D **skyline** of validator-approved outbreak signals (24h). Each tower is a
    pathogen; height = real validated count from ``signals.db``.
    """
    rows = ((realtime_data or {}).get("validated_disease_counts_24h") or [])
    pairs: list[tuple[str, int]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = str(r.get("disease") or "").strip()
        try:
            n = int(r.get("count") or 0)
        except (TypeError, ValueError):
            n = 0
        if d and n > 0:
            pairs.append((d, n))

    if not pairs:
        return _empty_state_figure(
            height,
            "No validator-approved signals in the last 24h yet — refresh data, or open Disease Surveillance.",
        )

    pairs.sort(key=lambda p: p[1], reverse=True)
    pairs = pairs[: max(1, int(max_diseases))]
    n_towers = len(pairs)

    cells = 14
    grid = max(36, cells * n_towers + 8)
    Z = np.zeros((cells + 4, grid), dtype=float)

    counts = np.array([c for _, c in pairs], dtype=float)
    cmax = float(counts.max() or 1.0)
    heights = (counts / cmax) * 2.4 + 0.18

    centers_x: list[float] = []
    for i, (_, _c) in enumerate(pairs):
        cx = 4 + i * cells + cells // 2
        centers_x.append(float(cx))
        h = float(heights[i])
        x_lo = cx - 4
        x_hi = cx + 4
        y_lo = 4
        y_hi = cells - 1
        Z[y_lo:y_hi, x_lo:x_hi] = h
        Z[y_lo - 1 : y_lo + 1, x_lo - 1 : x_hi + 1] = h * 0.55
        Z[y_hi - 1 : y_hi + 1, x_lo - 1 : x_hi + 1] = h * 0.55
        Z[y_lo - 1 : y_hi + 1, x_lo - 1 : x_lo + 1] = h * 0.55
        Z[y_lo - 1 : y_hi + 1, x_hi - 1 : x_hi + 1] = h * 0.55

    Y = np.arange(Z.shape[0])
    X = np.arange(Z.shape[1])

    fig = go.Figure(
        data=[
            go.Surface(
                x=X,
                y=Y,
                z=Z,
                colorscale=COOLIO_COLORSCALE,
                showscale=False,
                lighting=dict(ambient=0.55, diffuse=0.82, specular=0.38, roughness=0.38),
                hoverinfo="skip",
            )
        ]
    )

    label_y = float(Z.shape[0] - 1)
    fig.add_trace(
        go.Scatter3d(
            x=centers_x,
            y=[label_y] * n_towers,
            z=[float(h) + 0.18 for h in heights],
            mode="markers+text",
            marker=dict(size=4, color="#f8fafc", line=dict(width=0)),
            text=[f"<b>{d}</b><br>{c}" for d, c in pairs],
            textposition="top center",
            textfont=dict(size=11, color="#0f172a"),
            hovertext=[f"{d}: {c} validated signals (24h)" for d, c in pairs],
            hoverinfo="text",
            showlegend=False,
        )
    )
    fig.update_layout(**_coolio_scene(height))
    return fig


def coolio_forecast_hero_html(
    *,
    title: str,
    subtitle: str,
    signal_score: float,
    risk_level: str,
) -> str:
    esc = html_lib.escape
    sc = int(round(float(signal_score)))
    return f"""<div class="forecast-hero-shell">
<div class="forecast-hero-head">
  <div class="coolio-orb-wrap" aria-hidden="true"><div class="coolio-orb" title="Coolio — forecast intelligence layer"></div></div>
  <div>
    <div class="coolio-nameplate">Coolio · live outlook</div>
    <h1 class="coolio-hero-title">{esc(title)}</h1>
    <p class="coolio-hero-sub">{esc(subtitle)}</p>
    <div class="coolio-risk-chip"><span>Signal index</span><strong>{sc}/100</strong><span>·</span><span>{esc(str(risk_level))}</span></div>
  </div>
</div>
</div>"""


def coolio_dashboard_strip_html() -> str:
    """Compact banner for operational dashboards (e.g. national view)."""
    return """<div class="forecast-dash-banner">
<div class="mini-orb" aria-hidden="true"></div>
<div class="forecast-dash-banner-text">
<strong>Coolio</strong> — totals below combine live feeds and validator-approved signals.
<span class="forecast-dash-hint">Live 3D signal skyline is on <strong>Home</strong>.</span>
</div>
</div>"""
