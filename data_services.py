import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import StringIO
import os
import json
from pathlib import Path
import smtplib
from email.message import EmailMessage

import pandas as pd
import requests
import streamlit as st

ADMIN_ALERTS_FILE = Path("admin_alerts_config.json")


def read_csv_with_retry(url: str, attempts: int = 3, timeout_sec: int = 20):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=timeout_sec, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return pd.read_csv(StringIO(response.text))
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(1.4 ** attempt)
    raise RuntimeError(f"Failed to load CSV from {url}: {last_error}")


@st.cache_data(ttl=3600, show_spinner="Loading real malaria data for Uganda...")
def load_malaria_uganda_real():
    url = "https://ourworldindata.org/grapher/death-rate-from-malaria.csv"
    df = read_csv_with_retry(url)
    df_ug = df[df["Entity"] == "Uganda"].copy()
    df_ug = df_ug.sort_values("Year")
    df_ug = df_ug.rename(columns={"Death rate from malaria (per 100,000 population)": "death_rate"})
    return df_ug


def _http_headers():
    return {"User-Agent": "STI-EpiForecast/1.0 (Pathogen Economy dashboard; +https://github.com)"}


def _fetch_gdelt_hits(timeout_sec: float = 5) -> tuple[int, bool]:
    try:
        url = (
            "http://api.gdeltproject.org/api/v2/geo/geo?"
            "query=%22cholera+OR+malaria+OR+outbreak%22&"
            "mode=NewsArticles&format=json&timespan=1day"
        )
        r = requests.get(url, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return 0, False
        hits = int(r.json().get("meta", {}).get("totalhits", 0) or 0)
        return (hits, hits > 0)
    except Exception:
        return 0, False


def _fetch_reddit_recent_count(timeout_sec: float = 7) -> tuple[int, bool]:
    """Reddit public JSON search (last day); count is capped by Reddit (≤100)."""
    try:
        url = "https://www.reddit.com/search.json"
        params = {"q": "cholera OR malaria OR outbreak OR cholera uganda", "sort": "new", "t": "day", "limit": 100}
        r = requests.get(url, params=params, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return 0, False
        children = r.json().get("data", {}).get("children") or []
        return len(children), True
    except Exception:
        return 0, False


def _fetch_hn_algolia_hits(timeout_sec: float = 7) -> tuple[int, bool]:
    try:
        since = int(time.time()) - 86400
        url = "https://hn.algolia.com/api/v1/search"
        params = {
            "query": "cholera malaria outbreak epidemic",
            "tags": "story",
            "numericFilters": f"created_at_i>{since}",
        }
        r = requests.get(url, params=params, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return 0, False
        nb = int(r.json().get("nbHits", 0) or 0)
        return nb, True
    except Exception:
        return 0, False


def _fetch_newsapi_total(timeout_sec: float = 8) -> tuple[int, bool]:
    key = os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY")
    if not key:
        return 0, False
    try:
        from_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "(cholera OR malaria OR outbreak) AND (africa OR uganda OR health)",
            "language": "en",
            "from": from_date,
            "sortBy": "publishedAt",
            "pageSize": 1,
            "apiKey": key,
        }
        r = requests.get(url, params=params, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return 0, False
        total = int(r.json().get("totalResults", 0) or 0)
        return min(total, 5000), True
    except Exception:
        return 0, False


@st.cache_data(ttl=30, show_spinner="Refreshing outbreak + open-web feeds...")
def fetch_realtime_outbreak_data():
    """
    Short-TTL snapshot (~5s cache). Mixes:
    - GDELT: news article volume (24h).
    - Reddit public search, Hacker News (Algolia): real post/story counts (24h windows).
    - NewsAPI: optional when NEWSAPI_KEY is set.
    - Baseline outbreak KPIs: illustrative magnitudes (not MoH official).
    - Community channel: small simulated residual (no public API).
    """
    base_news = random.randint(900, 2000)
    gdelt_hits, gdelt_ok = 0, False
    reddit_n, reddit_ok = 0, False
    hn_n, hn_ok = 0, False
    newsapi_n, newsapi_ok = 0, False
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_fetch_gdelt_hits): "gdelt",
            pool.submit(_fetch_reddit_recent_count): "reddit",
            pool.submit(_fetch_hn_algolia_hits): "hn",
            pool.submit(_fetch_newsapi_total): "newsapi",
        }
        try:
            for fut in as_completed(futures, timeout=10):
                kind = futures[fut]
                try:
                    val = fut.result()
                except Exception:
                    continue
                if kind == "gdelt":
                    gdelt_hits, gdelt_ok = val
                elif kind == "reddit":
                    reddit_n, reddit_ok = val
                elif kind == "hn":
                    hn_n, hn_ok = val
                else:
                    newsapi_n, newsapi_ok = val
        except TimeoutError:
            pass

    news_mentions = gdelt_hits if gdelt_ok else base_news

    data = {
        "cholera_cases": 38000 + random.randint(-2500, 4500),
        "malaria_ug_cases_est": 12_000_000 + random.randint(-200_000, 400_000),
        "affected_countries": random.randint(18, 24),
        "news_mentions": news_mentions,
        "recent_alerts": [
            "Cholera – Eastern Africa cluster (simulated)",
            "Malaria – Northern Uganda high transmission (simulated)",
        ],
        "data_source": "OWID malaria (hourly cache) + open-web hooks + illustrative outbreak KPIs",
        "last_updated": datetime.now().strftime("%H:%M:%S EAT"),
        "gdelt_ok": gdelt_ok,
        "reddit_ok": reddit_ok,
        "hackernews_ok": hn_ok,
        "newsapi_ok": newsapi_ok,
        "social_sources_note": (
            "Open web: GDELT (news), Reddit public search, Hacker News (Algolia). "
            "NEWSAPI_KEY enables NewsAPI. X/Meta/TikTok require their own APIs — not polled here. "
            "One community row remains a qualitative simulation."
        ),
    }

    if gdelt_ok:
        data["cholera_cases"] += (news_mentions // 1000) * 800
        data["malaria_ug_cases_est"] += (news_mentions // 1000) * 6000
        data["data_source"] = "OWID malaria + GDELT/Reddit/HN (+NewsAPI if keyed) + illustrative KPIs"

    nm = int(data["news_mentions"])
    open_web_sum = nm + reddit_n + hn_n + (newsapi_n if newsapi_ok else 0)

    data["social_channels"] = {
        "News (GDELT 24h)": nm if gdelt_ok else max(1, int(nm * 0.55)),
        "Reddit (public, 24h)": reddit_n if reddit_ok else 0,
        "Hacker News (Algolia, 24h)": hn_n if hn_ok else 0,
    }
    if newsapi_ok:
        data["social_channels"]["NewsAPI (24h, keyed)"] = newsapi_n

    # Small qualitative proxy where no APIs exist (CHW / WhatsApp-style buzz).
    data["social_channels"]["Community / field buzz (sim.)"] = max(
        12, int(open_web_sum * random.uniform(0.02, 0.06) + random.randint(10, 120))
    )

    data["social_sentiment_index"] = round(
        max(-1.0, min(1.0, (reddit_n - hn_n) / max(200, open_web_sum) + random.uniform(-0.15, 0.15))), 2
    )
    data["social_urgency_score"] = min(100, 22 + open_web_sum // 40 + random.randint(0, 10))
    data["sim_recommended_tier"] = (
        "Surge" if data["social_urgency_score"] >= 72 else ("Elevated" if data["social_urgency_score"] >= 48 else "Routine")
    )
    return data


def _ai_env_credentials():
    api_key = (
        os.getenv("CURSOR_API_KEY")
        or os.getenv("AI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("XAI_API_KEY")
    )
    base_url = (
        os.getenv("CURSOR_API_BASE_URL")
        or os.getenv("AI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = os.getenv("CURSOR_AI_MODEL") or os.getenv("AI_MODEL") or "gpt-4o-mini"
    return api_key, base_url, model


@st.cache_data(ttl=120, show_spinner="Generating AI NLP alert summaries...")
def generate_ai_nlp_alerts(
    disease: str,
    news_mentions: int,
    cholera_cases: int,
    affected_countries: int,
):
    fallback_alerts = [
        f"NLP Alert • {disease} mention velocity is increasing in regional media clusters.",
        "NLP Alert • Public sentiment indicates concern around treatment and diagnostics access.",
        "NLP Alert • Border-adjacent locations are over-represented in current alert signals.",
        "NLP Alert • Recommendation: tighten surveillance reporting cycle to every 24 hours.",
    ]

    api_server_url = os.getenv("ALERTS_API_URL", "http://127.0.0.1:8000/v1/nlp-alerts")
    try:
        api_response = requests.post(
            api_server_url,
            json={
                "disease": disease,
                "news_mentions": news_mentions,
                "cholera_cases": cholera_cases,
                "affected_countries": affected_countries,
            },
            timeout=8,
        )
        api_response.raise_for_status()
        api_payload = api_response.json()
        alerts = api_payload.get("alerts", [])
        source = api_payload.get("source", "ai")
        if isinstance(alerts, list) and alerts:
            normalized = []
            for line in alerts[:4]:
                line = str(line).strip()
                if not line.startswith("NLP Alert"):
                    line = f"NLP Alert • {line}"
                normalized.append(line)
            if len(normalized) < 4:
                normalized.extend(fallback_alerts[: 4 - len(normalized)])
            return normalized[:4], ("ai" if source == "ai" else "fallback")
    except Exception:
        pass

    api_key, base_url, model = _ai_env_credentials()
    if not api_key:
        return fallback_alerts, "fallback"

    system_prompt = (
        "You are an epidemiology surveillance assistant. "
        "Write 4 concise alert bullets for a government outbreak dashboard. "
        "Each bullet must start with 'NLP Alert •'. Keep each bullet under 18 words."
    )
    user_prompt = (
        f"Disease: {disease}\n"
        f"News mentions (24h): {news_mentions}\n"
        f"Estimated cholera cases: {cholera_cases}\n"
        f"Affected countries: {affected_countries}\n"
        "Return exactly 4 bullet lines and no extra text."
    )

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            },
            timeout=20,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        cleaned = []
        for line in lines:
            if not line.startswith("NLP Alert"):
                line = f"NLP Alert • {line}"
            cleaned.append(line)
        if len(cleaned) < 4:
            cleaned.extend(fallback_alerts[: 4 - len(cleaned)])
        return cleaned[:4], "ai"
    except Exception:
        return fallback_alerts, "fallback"


def load_admin_alert_config() -> dict:
    default = {
        "enabled": False,
        "daily_hour_utc": 6,
        "risk_threshold": 72,
        "recipients": [],
        "last_daily_sent_utc": "",
        "last_emergency_sent_utc": "",
    }
    try:
        if not ADMIN_ALERTS_FILE.exists():
            return default
        parsed = json.loads(ADMIN_ALERTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            return default
        merged = {**default, **parsed}
        merged["recipients"] = [str(x).strip() for x in merged.get("recipients", []) if str(x).strip()]
        return merged
    except Exception:
        return default


def save_admin_alert_config(config: dict) -> None:
    payload = {
        "enabled": bool(config.get("enabled", False)),
        "daily_hour_utc": int(config.get("daily_hour_utc", 6)),
        "risk_threshold": int(config.get("risk_threshold", 72)),
        "recipients": [str(x).strip() for x in config.get("recipients", []) if str(x).strip()],
        "last_daily_sent_utc": str(config.get("last_daily_sent_utc", "")),
        "last_emergency_sent_utc": str(config.get("last_emergency_sent_utc", "")),
    }
    ADMIN_ALERTS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_utc_iso(value: str):
    try:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _smtp_env():
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    sender = os.getenv("ALERT_FROM_EMAIL", user).strip()
    use_tls = os.getenv("SMTP_USE_TLS", "1").strip().lower() in {"1", "true", "yes"}
    return host, port, user, password, sender, use_tls


def send_admin_email(subject: str, body_text: str, recipients: list[str]) -> tuple[bool, str]:
    host, port, user, password, sender, use_tls = _smtp_env()
    if not host or not sender or not recipients:
        return False, "SMTP config missing or no recipients"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body_text)
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, str(exc)[:240]


def analyze_outbreak_risk(realtime_data: dict) -> dict:
    social_urgency = int(realtime_data.get("social_urgency_score", 0))
    mentions = int(realtime_data.get("news_mentions", 0))
    countries = int(realtime_data.get("affected_countries", 0))
    score = min(100, max(0, int(social_urgency * 0.7 + mentions / 60 + countries * 1.1)))
    level = "High" if score >= 75 else ("Medium" if score >= 50 else "Low")
    return {
        "risk_score": score,
        "risk_level": level,
        "social_urgency": social_urgency,
        "mentions": mentions,
        "countries": countries,
    }


def build_admin_update_message(realtime_data: dict, risk: dict) -> str:
    disease = "Outbreak surveillance"
    alerts, _ = generate_ai_nlp_alerts(
        disease=disease,
        news_mentions=risk["mentions"],
        cholera_cases=int(realtime_data.get("cholera_cases", 0)),
        affected_countries=risk["countries"],
    )
    top_alerts = "\n".join(f"- {line}" for line in alerts[:3])
    return (
        "STI-EpiForecast App — Risk Update\n\n"
        f"Time (UTC): {_utc_now_iso()}\n"
        f"Risk level: {risk['risk_level']} ({risk['risk_score']}/100)\n"
        f"Signal mentions (24h): {risk['mentions']:,}\n"
        f"Affected countries: {risk['countries']}\n"
        f"Composite urgency: {risk['social_urgency']}/100\n\n"
        "AI analysis highlights:\n"
        f"{top_alerts}\n\n"
        "Source notes:\n"
        f"{realtime_data.get('social_sources_note', '')}\n"
    )


def evaluate_and_send_admin_notifications(realtime_data: dict) -> dict:
    config = load_admin_alert_config()
    result = {"sent_daily": False, "sent_emergency": False, "message": "disabled"}
    if not config.get("enabled"):
        return result
    recipients = config.get("recipients", [])
    if not recipients:
        return {"sent_daily": False, "sent_emergency": False, "message": "no recipients"}

    risk = analyze_outbreak_risk(realtime_data)
    now_utc = datetime.now(timezone.utc)
    body = build_admin_update_message(realtime_data, risk)

    # Daily summary window: first run after configured UTC hour.
    daily_hour = int(config.get("daily_hour_utc", 6))
    last_daily = _parse_utc_iso(config.get("last_daily_sent_utc", ""))
    due_daily = now_utc.hour >= daily_hour and (
        last_daily is None or last_daily.date() < now_utc.date()
    )
    if due_daily:
        ok, msg = send_admin_email(
            subject=f"[Daily] STI-EpiForecast {risk['risk_level']} risk",
            body_text=body,
            recipients=recipients,
        )
        if ok:
            config["last_daily_sent_utc"] = _utc_now_iso()
            result["sent_daily"] = True
        result["message"] = msg

    # Emergency trigger with cooldown.
    threshold = int(config.get("risk_threshold", 72))
    last_emergency = _parse_utc_iso(config.get("last_emergency_sent_utc", ""))
    emergency_due = risk["risk_score"] >= threshold and (
        last_emergency is None or (now_utc - last_emergency) >= timedelta(hours=8)
    )
    if emergency_due:
        ok, msg = send_admin_email(
            subject=f"[EMERGENCY] {risk['risk_level']} outbreak risk {risk['risk_score']}/100",
            body_text=body,
            recipients=recipients,
        )
        if ok:
            config["last_emergency_sent_utc"] = _utc_now_iso()
            result["sent_emergency"] = True
        result["message"] = msg

    save_admin_alert_config(config)
    return result


def _ai_chat_text(system_prompt: str, user_prompt: str, temperature: float = 0.25, timeout_sec: float = 35) -> str | None:
    api_key, base_url, model = _ai_env_credentials()
    if not api_key:
        return None
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            },
            timeout=timeout_sec,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _vdtec_fallback_catalog(host: str, disease: str, condition_class: str) -> list[dict]:
    """Rule-based VDTEC lines when AI is unavailable."""
    rows: list[dict] = []
    if condition_class != "Communicable":
        rows.extend(
            [
                {"Category": "Drug", "Product": f"First-line therapy pack — {disease}", "Licensed (Y/N)": "Y", "_qty_base": 120_000, "Unit": "course", "_rev_band": 4.2, "_roi_band": "1.4x – 2.1x", "_gou_return_low": 5.0, "_gou_return_high": 9.0, "_gou_invest": 4.0},
                {"Category": "Diagnostic", "Product": "Point-of-care metabolic panel", "Licensed (Y/N)": "Y", "_qty_base": 85_000, "Unit": "test", "_rev_band": 2.1, "_roi_band": "1.2x – 1.8x", "_gou_return_low": 2.5, "_gou_return_high": 4.2, "_gou_invest": 2.2},
                {"Category": "Medical device", "Product": "Home BP / glucose monitoring kit", "Licensed (Y/N)": "Y", "_qty_base": 200_000, "Unit": "kit", "_rev_band": 3.0, "_roi_band": "1.1x – 1.7x", "_gou_return_low": 3.0, "_gou_return_high": 5.0, "_gou_invest": 3.2},
            ]
        )
        if condition_class == "Trauma & injuries":
            rows.insert(
                0,
                {"Category": "Consumable", "Product": "Major haemorrhage pack (IV access + fluids)", "Licensed (Y/N)": "Y", "_qty_base": 45_000, "Unit": "pack", "_rev_band": 2.8, "_roi_band": "1.3x – 2.0x", "_gou_return_low": 3.5, "_gou_return_high": 6.0, "_gou_invest": 3.0},
            )
        return rows

    if disease == "Malaria":
        vac_note = "RTS,S / R21 (partial protection)"
    else:
        vac_note = disease
    human_vac_lic = "N" if disease in ("Marburg", "HIV/AIDS") else "Y"

    if host == "Human":
        rows = [
            {"Category": "Vaccine", "Product": f"Primary vaccine candidate — {vac_note}", "Licensed (Y/N)": human_vac_lic, "_qty_base": 2_400_000, "Unit": "dose", "_rev_band": 18.0, "_roi_band": "2.0x – 3.8x", "_gou_return_low": 40.0, "_gou_return_high": 95.0, "_gou_invest": 22.0},
            {"Category": "Drug", "Product": f"Antimicrobial / antiviral course — {disease}", "Licensed (Y/N)": "Y", "_qty_base": 800_000, "Unit": "course", "_rev_band": 9.0, "_roi_band": "1.5x – 2.4x", "_gou_return_low": 12.0, "_gou_return_high": 22.0, "_gou_invest": 8.0},
            {"Category": "Diagnostic", "Product": f"RDT / PCR tier-1 — {disease}", "Licensed (Y/N)": "Y", "_qty_base": 1_100_000, "Unit": "test", "_rev_band": 6.5, "_roi_band": "1.3x – 2.0x", "_gou_return_low": 7.0, "_gou_return_high": 13.0, "_gou_invest": 5.5},
            {"Category": "Consumable", "Product": "PPE + safe injection set (national buffer)", "Licensed (Y/N)": "Y", "_qty_base": 3_500_000, "Unit": "procedure pack", "_rev_band": 5.0, "_roi_band": "1.1x – 1.6x", "_gou_return_low": 5.0, "_gou_return_high": 8.0, "_gou_invest": 4.5},
            {"Category": "Medical device", "Product": "Oxygen concentrators + consumables", "Licensed (Y/N)": "Y", "_qty_base": 12_000, "Unit": "device", "_rev_band": 7.0, "_roi_band": "1.2x – 1.9x", "_gou_return_low": 6.0, "_gou_return_high": 11.0, "_gou_invest": 5.0},
        ]
        if disease == "Marburg":
            rows[0]["Licensed (Y/N)"] = "N"
            rows[0]["Product"] = "Filovirus vaccine candidate (no routine licensed vaccine)"
    elif host == "Animal":
        rows = [
            {"Category": "Vaccine", "Product": f"Sector vaccine — {disease}", "Licensed (Y/N)": "N" if disease in ("African swine fever",) else "Y", "_qty_base": 1_200_000, "Unit": "dose", "_rev_band": 6.0, "_roi_band": "1.4x – 2.2x", "_gou_return_low": 8.0, "_gou_return_high": 15.0, "_gou_invest": 6.0},
            {"Category": "Drug", "Product": "Anthelmintic / antimicrobial surge pack", "Licensed (Y/N)": "Y", "_qty_base": 400_000, "Unit": "course", "_rev_band": 3.5, "_roi_band": "1.2x – 1.8x", "_gou_return_low": 4.0, "_gou_return_high": 7.0, "_gou_invest": 3.5},
            {"Category": "Diagnostic", "Product": "Vet-side serology / antigen RDT", "Licensed (Y/N)": "Y", "_qty_base": 250_000, "Unit": "test", "_rev_band": 2.0, "_roi_band": "1.1x – 1.6x", "_gou_return_low": 2.0, "_gou_return_high": 3.5, "_gou_invest": 1.8},
            {"Category": "Consumable", "Product": "Cold chain consumables + PPE", "Licensed (Y/N)": "Y", "_qty_base": 600_000, "Unit": "kit", "_rev_band": 1.5, "_roi_band": "1.0x – 1.5x", "_gou_return_low": 1.5, "_gou_return_high": 2.5, "_gou_invest": 1.4},
            {"Category": "Medical device", "Product": "Portable ultrasound / dosing equipment", "Licensed (Y/N)": "Y", "_qty_base": 2_500, "Unit": "unit", "_rev_band": 2.2, "_roi_band": "1.1x – 1.7x", "_gou_return_low": 2.5, "_gou_return_high": 4.0, "_gou_invest": 2.0},
        ]
    else:
        rows = [
            {"Category": "Vaccine", "Product": "Prophylactic / biocontrol programme (no classical vaccine)", "Licensed (Y/N)": "N", "_qty_base": 50_000, "Unit": "ha-pack", "_rev_band": 0.8, "_roi_band": "1.0x – 1.4x", "_gou_return_low": 0.8, "_gou_return_high": 1.4, "_gou_invest": 0.7},
            {"Category": "Drug", "Product": f"Registered fungicide / bactericide — {disease}", "Licensed (Y/N)": "Y", "_qty_base": 400_000, "Unit": "L", "_rev_band": 3.0, "_roi_band": "1.2x – 1.9x", "_gou_return_low": 3.0, "_gou_return_high": 5.5, "_gou_invest": 2.5},
            {"Category": "Diagnostic", "Product": "Field / lab pathogen detection kit", "Licensed (Y/N)": "Y", "_qty_base": 180_000, "Unit": "assay", "_rev_band": 1.8, "_roi_band": "1.1x – 1.7x", "_gou_return_low": 2.0, "_gou_return_high": 3.2, "_gou_invest": 1.6},
            {"Category": "Consumable", "Product": "Vector control + PPE for field teams", "Licensed (Y/N)": "Y", "_qty_base": 220_000, "Unit": "team-day", "_rev_band": 1.2, "_roi_band": "1.0x – 1.4x", "_gou_return_low": 1.2, "_gou_return_high": 1.8, "_gou_invest": 1.1},
            {"Category": "Medical device", "Product": "Irrigation / sensor hardware (precision control)", "Licensed (Y/N)": "Y", "_qty_base": 4_000, "Unit": "node", "_rev_band": 2.5, "_roi_band": "1.1x – 1.8x", "_gou_return_low": 2.5, "_gou_return_high": 4.0, "_gou_invest": 2.0},
        ]
    return rows


def _normalize_vdtec_df(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    if "Product" in df.columns and "Product / intervention" not in df.columns:
        df = df.rename(columns={"Product": "Product / intervention"})
    if "Unit" in df.columns and "Unit (illustrative)" not in df.columns:
        df = df.rename(columns={"Unit": "Unit (illustrative)"})
    return df


@st.cache_data(ttl=180, show_spinner="Building VDTEC countermeasure rows...")
def generate_pe_countermeasures_rows(
    host: str,
    disease: str,
    condition_class: str,
    risk_score: int,
    use_ai: bool,
) -> pd.DataFrame:
    base = _vdtec_fallback_catalog(host, disease, condition_class)
    df = _normalize_vdtec_df(pd.DataFrame(base))
    if not use_ai:
        return df

    system = (
        "Return ONLY valid JSON: an array of 5-8 objects with keys "
        "category (one of Vaccine, Drug, Diagnostic, Consumable, Medical device), "
        "product (short name), licensed_y (Y or N for whether a licensed human/vet/plant product exists today), "
        "qty_base (integer baseline national 100-day units), unit (string), "
        "rev_band_m (number, USD millions Year-1 revenue band mid), "
        "roi_band (string like 1.2x-2.0x), gou_return_low_m, gou_return_high_m, gou_invest_m (numbers)."
    )
    user = (
        f"Host: {host}. Disease/condition: {disease}. Class: {condition_class}. Risk score 0-100: {risk_score}. "
        "Prioritize Uganda Pathogen Economy VDTEC planning."
    )
    raw = _ai_chat_text(system, user, temperature=0.2)
    if not raw:
        return _normalize_vdtec_df(df)
    try:
        blob = raw.strip()
        if blob.startswith("```"):
            blob = blob.split("```", 2)[1]
            if blob.lower().startswith("json"):
                blob = blob[4:]
        data = json.loads(blob)
        if not isinstance(data, list):
            return _normalize_vdtec_df(df)
        mapped = []
        for item in data[:10]:
            if not isinstance(item, dict):
                continue
            cat = str(item.get("category", "Drug")).title()
            if cat not in {"Vaccine", "Drug", "Diagnostic", "Consumable", "Medical device"}:
                cat = "Drug"
            lic = "Y" if str(item.get("licensed_y", "Y")).upper().startswith("Y") else "N"
            mapped.append(
                {
                    "Category": cat,
                    "Product / intervention": str(item.get("product", "Countermeasure"))[:120],
                    "Licensed (Y/N)": lic,
                    "_qty_base": int(item.get("qty_base", 100_000)),
                    "Unit (illustrative)": str(item.get("unit", "unit"))[:40],
                    "_rev_band": float(item.get("rev_band_m", 2.0)),
                    "_roi_band": str(item.get("roi_band", "1.2x – 1.8x"))[:32],
                    "_gou_return_low": float(item.get("gou_return_low_m", 2.0)),
                    "_gou_return_high": float(item.get("gou_return_high_m", 4.0)),
                    "_gou_invest": float(item.get("gou_invest_m", 1.5)),
                }
            )
        if mapped:
            return pd.DataFrame(mapped)
    except Exception:
        pass
    return _normalize_vdtec_df(df)


def generate_venture_matrix_ai(refresh: bool = False) -> pd.DataFrame:
    defaults = [
        ("TRL / product maturity", 0.14, 62, "Science → pilot → scale"),
        ("Regulatory & quality pathway", 0.16, 55, "NAFDAC / UVRI / MoH alignment"),
        ("Domestic market absorption (NMS)", 0.12, 70, "Shelf space & reimbursement"),
        ("IP & freedom to operate", 0.10, 48, "Patent landscape risk"),
        ("Team & governance", 0.12, 66, "PE bureau execution bandwidth"),
        ("Co-finance & offtake", 0.14, 52, "DFI / private anchor orders"),
        ("7-1-7 impact elasticity", 0.10, 74, "Early detection value"),
        ("EAC export readiness", 0.12, 58, "DRC / KEN border demand"),
    ]
    rows = [{"Variable": a, "Weight (0–1)": b, "Project score (0–100)": c, "Notes": d} for a, b, c, d in defaults]
    df = pd.DataFrame(rows)
    if not refresh:
        return df

    system = (
        "Return ONLY JSON array of 6-10 objects: variable, weight (0-1), score (0-100), note. "
        "Variables should guide STI funding decisions for Ugandan health/biotech ventures."
    )
    raw = _ai_chat_text(system, "Generate the matrix.", temperature=0.35)
    if not raw:
        return df
    try:
        blob = raw.strip()
        if blob.startswith("```"):
            blob = blob.split("```", 2)[1]
            if blob.lower().startswith("json"):
                blob = blob[4:]
        data = json.loads(blob)
        if not isinstance(data, list):
            return df
        out = []
        for item in data[:12]:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "Variable": str(item.get("variable", "Factor"))[:80],
                    "Weight (0–1)": float(item.get("weight", 0.1)),
                    "Project score (0–100)": float(item.get("score", 50)),
                    "Notes": str(item.get("note", ""))[:120],
                }
            )
        if out:
            return pd.DataFrame(out)
    except Exception:
        pass
    return df
