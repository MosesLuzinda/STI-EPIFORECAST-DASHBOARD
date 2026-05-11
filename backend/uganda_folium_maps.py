"""Reusable Folium maps: Uganda district risk layers + clinical / trial sites."""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.uganda_geospatial_data import CLINICAL_TRIAL_SITES, centroid_for_district


def _risk_color_from_label(label: str) -> str:
    t = (label or "").lower()
    if "high" in t or "surge" in t or "iii" in t:
        return "#dc2626"
    if "medium" in t or "phase ii" in t or "feasibility" in t:
        return "#d97706"
    return "#16a34a"


def _row_marker_color(row) -> str:
    lab = str(row.get("RiskLabel") or row.get("Trial fit") or "").strip()
    if lab:
        return _risk_color_from_label(lab)
    r = float(row.get("RiskScore") or row.get("Spatial risk score") or 0.0)
    if r > 0.65:
        return "#dc2626"
    if r > 0.52:
        return "#d97706"
    return "#16a34a"


def build_uganda_operational_map(
    district_df: pd.DataFrame,
    *,
    focus_disease: str,
    subtitle: str = "",
    show_heatmap: bool = True,
    show_clinical_layer: bool = True,
    zoom_start: int = 7,
    center: tuple[float, float] = (1.2, 32.2),
) -> Any | None:
    """
    Folium map: district CircleMarkers + optional HeatMap + clinical site markers + layer control.

    `district_df` must include: District, RiskScore, RiskLabel (optional: Trend, Estimated Cases,
    Spatial risk score, Trial fit).
    Returns None if folium unavailable.
    """
    try:
        import folium
        from folium.plugins import Fullscreen, HeatMap, LayerControl
    except ImportError:
        return None

    m = folium.Map(
        location=list(center),
        zoom_start=zoom_start,
        tiles="CartoDB dark_matter",
        control_scale=True,
    )

    fg_districts = folium.FeatureGroup(name="District risk", show=True)
    heat_points: list[list[float]] = []

    for _, row in district_df.iterrows():
        dist = str(row.get("District") or "").strip()
        if not dist:
            continue
        ll = centroid_for_district(dist)
        if ll is None:
            continue
        lat, lon = ll
        risk = float(row.get("RiskScore") or row.get("Spatial risk score") or 0.0)
        label = str(row.get("RiskLabel") or row.get("Trial fit") or "—")
        trend = str(row.get("Trend") or "—")
        est = row.get("Estimated Cases (14d)", row.get("Estimated cases (14d)"))
        try:
            est_txt = f"{int(float(est)):,}" if est is not None and not pd.isna(est) else "—"
        except (TypeError, ValueError):
            est_txt = "—"
        rationale = str(row.get("Rationale") or "").strip()

        radius = max(8, min(42, 10 + risk * 34))
        color = _row_marker_color(row)
        popup_html = (
            f"<div style='min-width:220px;font-size:13px'>"
            f"<b>{dist}</b><br/>"
            f"<b>Risk score:</b> {risk:.2f}<br/>"
            f"<b>Band / trial fit:</b> {label}<br/>"
            f"<b>Trend:</b> {trend}<br/>"
            f"<b>Est. cases (14d, proxy):</b> {est_txt}<br/>"
        )
        if rationale:
            popup_html += f"<br/><i>{rationale[:280]}{'…' if len(rationale) > 280 else ''}</i>"
        popup_html += f"<br/><small>Pathogen focus: {focus_disease}</small></div>"

        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.55,
            weight=2,
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=f"{dist}: {risk:.2f} ({label})",
        ).add_to(fg_districts)

        if show_heatmap:
            heat_points.append([lat, lon, max(0.15, risk**1.25)])

    fg_districts.add_to(m)

    if show_heatmap and heat_points:
        HeatMap(
            heat_points,
            min_opacity=0.25,
            max_zoom=10,
            radius=28,
            blur=22,
            gradient={0.2: "#1e3a5f", 0.45: "#f59e0b", 0.75: "#ef4444", 1.0: "#7f1d1d"},
        ).add_to(m)

    if show_clinical_layer:
        fg_clin = folium.FeatureGroup(name="Clinical & trial sites", show=True)
        for site in CLINICAL_TRIAL_SITES:
            lat = float(site["lat"])
            lon = float(site["lon"])
            name = str(site.get("name") or "")
            short = str(site.get("short") or "")
            d = str(site.get("district") or "")
            tier = str(site.get("tier") or "")
            role = str(site.get("role") or "")
            html = (
                f"<div style='min-width:240px;font-size:13px'>"
                f"<b>{name}</b> ({short})<br/>"
                f"<b>District:</b> {d}<br/>"
                f"<b>Tier:</b> {tier}<br/>"
                f"<b>Role:</b> {role}<br/>"
                f"<small>Illustrative anchor points — verify with MoH accreditation lists.</small>"
                f"</div>"
            )
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(html, max_width=340),
                tooltip=f"{short}: {tier}",
                icon=folium.Icon(color="blue", icon="plus-sign", prefix="glyphicon"),
            ).add_to(fg_clin)
        fg_clin.add_to(m)

    LayerControl(position="topright", collapsed=False).add_to(m)
    Fullscreen(position="topleft").add_to(m)

    title_html = (
        f'<div style="position:fixed;top:10px;left:52px;z-index:9999;background:rgba(15,23,42,0.88);'
        f'color:#f8fafc;padding:10px 14px;border-radius:10px;font-size:14px;max-width:420px;border:1px solid #334155">'
        f"<b>Uganda — operational map</b><br/>"
        f"<span style=\"color:#94a3b8\">{focus_disease}</span>"
        f"{(' · ' + subtitle) if subtitle else ''}</div>"
    )
    m.get_root().html.add_child(folium.Element(title_html))

    pts: list[list[float]] = []
    for _, row in district_df.iterrows():
        ll = centroid_for_district(str(row.get("District") or ""))
        if ll:
            pts.append([ll[0], ll[1]])
    if show_clinical_layer:
        for s in CLINICAL_TRIAL_SITES:
            pts.append([float(s["lat"]), float(s["lon"])])
    if len(pts) >= 2:
        south = min(p[0] for p in pts) - 0.35
        north = max(p[0] for p in pts) + 0.35
        west = min(p[1] for p in pts) - 0.35
        east = max(p[1] for p in pts) + 0.35
        m.fit_bounds([[south, west], [north, east]])

    return m


def streamlit_folium_available() -> bool:
    try:
        import folium  # noqa: F401
        from streamlit_folium import st_folium  # noqa: F401
    except ImportError:
        return False
    return True
