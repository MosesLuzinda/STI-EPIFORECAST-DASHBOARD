"""
Uganda district centroids and clinical / trial site anchors for mapping.

Coordinates are approximate district administrative centres for visualization only;
replace with UBOS / MoH authoritative geometry when available.
"""
from __future__ import annotations

# Major districts used in planning views — (lat, lon) WGS84
UGANDA_DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "Kampala": (0.3476, 32.5825),
    "Wakiso": (0.3980, 32.4597),
    "Mukono": (0.3533, 32.7553),
    "Jinja": (0.4244, 33.2042),
    "Entebbe": (0.0562, 32.4775),
    "Gulu": (2.7747, 32.2989),
    "Lira": (2.2470, 32.8997),
    "Kitgum": (3.2780, 32.8867),
    "Arua": (3.0197, 30.9077),
    "Nebbi": (2.4780, 31.0880),
    "Yumbe": (3.4651, 31.2465),
    "Adjumani": (3.3779, 31.7912),
    "Mbale": (1.0809, 34.1750),
    "Soroti": (1.7146, 33.6111),
    "Tororo": (0.6928, 34.1808),
    "Busia": (0.4667, 34.0900),
    "Kasese": (0.1836, 30.0833),
    "Fort Portal": (0.6710, 30.2747),
    "Hoima": (1.4333, 31.3667),
    "Masindi": (1.6744, 31.7150),
    "Mbarara": (-0.6049, 30.6486),
    "Kabale": (-1.2483, 29.9899),
    "Rukungiri": (-0.8411, 29.9414),
    "Ntungamo": (-0.9144, 30.2381),
    "Masaka": (-0.3333, 31.7333),
    "Lwengo": (-0.4167, 31.4167),
    "Mubende": (0.5575, 31.3950),
    "Kyegegwa": (0.4850, 31.0640),
    "Kyenjojo": (0.6225, 30.6458),
    "Kamuli": (0.9472, 33.1200),
    "Iganga": (0.6092, 33.4686),
    "Moroto": (2.5347, 34.6686),
    "Kotido": (2.9806, 34.1108),
    "Kalangala": (-0.3089, 32.2931),
}

# Referral hospitals, labs, and typical high-enrollment trial anchors (illustrative)
CLINICAL_TRIAL_SITES: list[dict[str, str | float]] = [
    {
        "name": "Mulago National Referral Hospital",
        "short": "Mulago NRH",
        "lat": 0.3375,
        "lon": 32.5744,
        "district": "Kampala",
        "tier": "National referral",
        "role": "Phase II–IV clinical trials, tertiary ID & surgery",
    },
    {
        "name": "Uganda Virus Research Institute",
        "short": "UVRI",
        "lat": 0.0519,
        "lon": 32.4608,
        "district": "Wakiso",
        "tier": "BSL-3 / national lab",
        "role": "Viral diagnostics, vaccine field studies, outbreak lab hub",
    },
    {
        "name": "Joint Clinical Research Centre",
        "short": "JCRC",
        "lat": 0.3186,
        "lon": 32.5911,
        "district": "Kampala",
        "tier": "Research clinic",
        "role": "HIV/TB prevention & treatment trials",
    },
    {
        "name": "Infectious Diseases Institute",
        "short": "IDI",
        "lat": 0.3402,
        "lon": 32.6022,
        "district": "Kampala",
        "tier": "Academic clinical unit",
        "role": "Infectious disease trials, cohort platforms",
    },
    {
        "name": "Mbarara Regional Referral Hospital",
        "short": "Mbarara RRH",
        "lat": -0.6050,
        "lon": 30.6486,
        "district": "Mbarara",
        "tier": "Regional referral",
        "role": "South-west surveillance + multi-site trial node",
    },
    {
        "name": "Gulu Regional Referral Hospital",
        "short": "Gulu RRH",
        "lat": 2.7747,
        "lon": 32.2989,
        "district": "Gulu",
        "tier": "Regional referral",
        "role": "Northern hub; refugee-adjacent studies",
    },
    {
        "name": "Mbale Regional Referral Hospital",
        "short": "Mbale RRH",
        "lat": 1.0809,
        "lon": 34.1750,
        "district": "Mbale",
        "tier": "Regional referral",
        "role": "Eastern border corridor trials",
    },
    {
        "name": "Fort Portal Regional Referral Hospital",
        "short": "Fort Portal RRH",
        "lat": 0.6710,
        "lon": 30.2747,
        "district": "Fort Portal",
        "tier": "Regional referral",
        "role": "DRC-border EVD preparedness node",
    },
    {
        "name": "Hoima Regional Referral Hospital",
        "short": "Hoima RRH",
        "lat": 1.4333,
        "lon": 31.3667,
        "district": "Hoima",
        "tier": "Regional referral",
        "role": "Oil corridor / mobility demographic catchment",
    },
    {
        "name": "Lira Regional Referral Hospital",
        "short": "Lira RRH",
        "lat": 2.2470,
        "lon": 32.8997,
        "district": "Lira",
        "tier": "Regional referral",
        "role": "Northern belt sentinel site",
    },
    {
        "name": "St. Mary’s Lacor Hospital",
        "short": "Lacor",
        "lat": 2.7667,
        "lon": 32.3050,
        "district": "Gulu",
        "tier": "Faith-based referral",
        "role": "High-volume fMPXV / outbreak cohort capacity",
    },
    {
        "name": "Tororo District Hospital",
        "short": "Tororo DH",
        "lat": 0.6928,
        "lon": 34.1808,
        "district": "Tororo",
        "tier": "District + border",
        "role": "Malaria vaccine & border surveillance legacy site",
    },
]


def centroid_for_district(name: str) -> tuple[float, float] | None:
    key = (name or "").strip()
    if not key:
        return None
    if key in UGANDA_DISTRICT_CENTROIDS:
        return UGANDA_DISTRICT_CENTROIDS[key]
    low = key.lower()
    for k, v in UGANDA_DISTRICT_CENTROIDS.items():
        if k.lower() == low:
            return v
    return None


def default_hotspot_district_bases() -> list[tuple[str, float]]:
    """(District, baseline spatial risk 0–1) for vulnerability modelling."""
    return [
        ("Kampala", 0.72),
        ("Wakiso", 0.68),
        ("Mukono", 0.62),
        ("Jinja", 0.58),
        ("Gulu", 0.58),
        ("Arua", 0.61),
        ("Mbale", 0.55),
        ("Soroti", 0.54),
        ("Tororo", 0.56),
        ("Kasese", 0.68),
        ("Fort Portal", 0.57),
        ("Hoima", 0.56),
        ("Mbarara", 0.50),
        ("Lira", 0.53),
        ("Moroto", 0.48),
        ("Mubende", 0.64),
        ("Kamuli", 0.52),
        ("Entebbe", 0.60),
        ("Adjumani", 0.49),
        ("Masaka", 0.51),
    ]
