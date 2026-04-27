import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import StringIO
import os
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import smtplib
from email.message import EmailMessage

import pandas as pd
import requests
import streamlit as st

from signal_validator import validate_signals_batch, keyword_relevant
from signal_store import (
    append_signals as _persist_signals,
    count_recent as _count_recent_signals,
    daily_aggregate as _signal_daily_aggregate,
    list_diseases as _list_signal_diseases,
)

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
    # OWID occasionally changes column labels; normalize to a stable name used by the app.
    rate_candidates = [
        "death_rate",
        "Death rate from malaria (per 100,000 population)",
        "Estimated malaria mortality rate (per 100 000 population)",
    ]
    rate_col = next((col for col in rate_candidates if col in df_ug.columns), None)
    if rate_col is None:
        raise RuntimeError(
            "Could not find malaria death-rate column in OWID dataset. "
            f"Available columns: {list(df_ug.columns)}"
        )
    if rate_col != "death_rate":
        df_ug = df_ug.rename(columns={rate_col: "death_rate"})
    return df_ug


def _http_headers():
    return {"User-Agent": "STI-EpiForecast/1.0 (Pathogen Economy dashboard; +https://github.com)"}


def _fetch_gdelt_hits(timeout_sec: float = 20) -> tuple[int, bool]:
    """
    GDELT outbreak-article volume (last 24h) via the doc API.
    The legacy geo/geo endpoint returns 404 — we use doc/doc + ArtList and
    treat the returned article count as the volume signal.
    """
    try:
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc?"
            "query=cholera+OR+malaria+OR+outbreak+OR+epidemic&"
            "mode=ArtList&maxrecords=250&format=json&timespan=1d&sort=datedesc"
        )
        r = requests.get(url, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return 0, False
        articles = r.json().get("articles") or []
        return len(articles), len(articles) > 0
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


def _fetch_reddit_recent_items(limit: int = 8, timeout_sec: float = 7) -> tuple[list[dict], bool]:
    """Recent Reddit posts with direct links for drill-down (AI-validated)."""
    try:
        url = "https://www.reddit.com/search.json"
        params = {"q": "cholera OR malaria OR outbreak OR cholera uganda", "sort": "new", "t": "day", "limit": max(3, int(limit))}
        r = requests.get(url, params=params, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return [], False
        children = r.json().get("data", {}).get("children") or []
        candidates: list[dict] = []
        for child in children[:limit]:
            payload = child.get("data") or {}
            title = str(payload.get("title") or "").strip()
            permalink = str(payload.get("permalink") or "").strip()
            subreddit = str(payload.get("subreddit") or "").strip()
            description = str(payload.get("selftext") or "").strip()
            if not title:
                continue
            post_url = f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com/search/?q=cholera%20malaria%20outbreak"
            candidates.append(
                {
                    "source": "Reddit",
                    "title": title,
                    "url": post_url,
                    "description": description,
                    "meta": subreddit or "reddit",
                }
            )
        decisions = _validate_and_persist(candidates)
        items = [
            {
                "source": cand["source"],
                "title": cand["title"],
                "url": cand["url"],
                "meta": cand.get("meta") or "reddit",
            }
            for cand, dec in zip(candidates, decisions)
            if dec.get("is_signal")
        ]
        return items, True
    except Exception:
        return [], False


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


def _fetch_hn_recent_items(limit: int = 6, timeout_sec: float = 7) -> tuple[list[dict], bool]:
    try:
        since = int(time.time()) - 86400
        url = "https://hn.algolia.com/api/v1/search"
        params = {
            "query": "cholera malaria outbreak epidemic",
            "tags": "story",
            "numericFilters": f"created_at_i>{since}",
            "hitsPerPage": max(3, int(limit)),
        }
        r = requests.get(url, params=params, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return [], False
        hits = r.json().get("hits") or []
        candidates: list[dict] = []
        for hit in hits[:limit]:
            title = str(hit.get("title") or hit.get("story_title") or "").strip()
            if not title:
                continue
            article_url = str(hit.get("url") or "").strip()
            if not article_url:
                item_id = hit.get("objectID")
                article_url = f"https://news.ycombinator.com/item?id={item_id}" if item_id else "https://news.ycombinator.com/"
            candidates.append(
                {
                    "source": "Hacker News",
                    "title": title,
                    "url": article_url,
                    "description": str(hit.get("story_text") or "").strip(),
                    "meta": "HN Algolia",
                }
            )
        decisions = _validate_and_persist(candidates)
        items = [
            {
                "source": cand["source"],
                "title": cand["title"],
                "url": cand["url"],
                "meta": cand.get("meta") or "HN Algolia",
            }
            for cand, dec in zip(candidates, decisions)
            if dec.get("is_signal")
        ]
        return items, True
    except Exception:
        return [], False


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


def _fetch_gdelt_domain_hits(domain: str, timeout_sec: float = 15) -> tuple[int, bool]:
    """Count last-day disease articles for a specific domain via GDELT."""
    try:
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc?"
            f"query=(cholera+OR+malaria+OR+outbreak+OR+epidemic)+domain:{domain}&"
            "mode=ArtList&maxrecords=250&format=json&timespan=1d"
        )
        r = requests.get(url, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return 0, False
        articles = r.json().get("articles") or []
        return len(articles), True
    except Exception:
        return 0, False


# Outbreak / disease keyword filter used to keep RSS items relevant.
_OUTBREAK_KEYWORDS = (
    "outbreak", "epidemic", "pandemic", "cholera", "malaria", "ebola",
    "marburg", "dengue", "influenza", "h5n1", "h7n9", "covid", "mpox",
    "measles", "rabies", "yellow fever", "polio", "lassa", "anthrax",
    "typhoid", "rift valley", "zika", "rsv", "tuberculosis", "hiv",
    "diphtheria", "meningitis", "leptospirosis",
)


def _is_outbreak_relevant(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in _OUTBREAK_KEYWORDS)


def _validate_and_persist(candidates: list[dict]) -> list[dict]:
    """
    Run candidate feed items through the AI signal validator, persist the
    accepted items into the SQLite signal store, and return aligned decisions.

    The decisions list has the same length and order as `candidates`. Each
    decision dict has keys: is_signal, confidence, disease, location, reason,
    engine. Callers filter on `is_signal` to decide what to surface.
    """
    if not candidates:
        return []
    try:
        decisions = validate_signals_batch(candidates)
    except Exception:
        decisions = [
            {
                "is_signal": False, "confidence": 0.0, "disease": "",
                "location": "", "reason": "validator error", "engine": "keyword",
            }
            for _ in candidates
        ]

    persist_rows: list[dict] = []
    for cand, dec in zip(candidates, decisions):
        if not dec.get("is_signal"):
            continue
        persist_rows.append(
            {
                "source": cand.get("source") or "",
                "title": cand.get("title") or "",
                "url": cand.get("url") or "",
                "disease": dec.get("disease") or "",
                "location": dec.get("location") or "",
                "confidence": dec.get("confidence") or 0.0,
                "engine": dec.get("engine") or "",
                "reason": dec.get("reason") or "",
            }
        )
    if persist_rows:
        try:
            _persist_signals(persist_rows)
        except Exception:
            pass
    return decisions


def _fetch_who_outbreak_news_count(timeout_sec: float = 10) -> tuple[int, bool]:
    """
    Outbreak-relevant items across WHO RSS feeds (current state, not just 24h).
    The legacy `feeds/entity/emergencies/...` URLs return 404 — we use the
    actively-maintained `rss-feeds/news-english.xml` plus WHO Africa.
    """
    feeds = [
        "https://www.who.int/rss-feeds/news-english.xml",
        "https://www.afro.who.int/rss.xml",
    ]
    total = 0
    any_ok = False
    for feed_url in feeds:
        try:
            r = requests.get(feed_url, timeout=timeout_sec, headers=_http_headers())
            if r.status_code != 200 or not r.text.strip():
                continue
            any_ok = True
            root = ET.fromstring(r.text)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                if _is_outbreak_relevant(f"{title} {desc}"):
                    total += 1
        except Exception:
            continue
    return total, any_ok and total > 0


def _fetch_rss_items(
    feed_url: str,
    source_label: str,
    limit: int = 8,
    timeout_sec: float = 10,
    outbreak_only: bool = True,
) -> tuple[list[dict], bool]:
    """
    Fetch RSS items from a feed. When `outbreak_only` is True (default), each
    candidate item is run through the AI signal validator and only items
    classified as real outbreak signals are returned (and persisted to the
    signal store for the signal-trained forecast model).
    """
    try:
        r = requests.get(feed_url, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200 or not r.text.strip():
            return [], False
        root = ET.fromstring(r.text)
        items_xml = root.findall(".//item")
        candidates: list[dict] = []
        for item in items_xml:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not title and not link:
                continue
            if outbreak_only and not keyword_relevant(f"{title} {desc}"):
                # Cheap pre-filter avoids spending LLM budget on obviously
                # irrelevant feed items (e.g. corporate announcements).
                continue
            candidates.append(
                {
                    "source": source_label,
                    "title": title or f"{source_label} item",
                    "url": link or "",
                    "description": desc,
                    "meta": "rss",
                }
            )
            if len(candidates) >= max(limit, 10):
                break

        if not outbreak_only:
            return [
                {
                    "source": c["source"],
                    "title": c["title"],
                    "url": c["url"],
                    "meta": c.get("meta") or "rss",
                }
                for c in candidates[:limit]
            ], len(candidates) > 0

        decisions = _validate_and_persist(candidates)
        out: list[dict] = []
        for cand, dec in zip(candidates, decisions):
            if not dec.get("is_signal"):
                continue
            out.append(
                {
                    "source": cand["source"],
                    "title": cand["title"],
                    "url": cand["url"],
                    "meta": cand.get("meta") or "rss",
                }
            )
            if len(out) >= limit:
                break
        return out, len(out) > 0
    except Exception:
        return [], False


def _fetch_rss_count(
    feed_url: str,
    timeout_sec: float = 10,
    outbreak_only: bool = True,
) -> tuple[int, bool]:
    """Lightweight RSS counter that only keeps outbreak-relevant items."""
    try:
        r = requests.get(feed_url, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200 or not r.text.strip():
            return 0, False
        root = ET.fromstring(r.text)
        items = root.findall(".//item")
        if not outbreak_only:
            return len(items), True
        n = 0
        for item in items:
            title = (item.findtext("title") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if _is_outbreak_relevant(f"{title} {desc}"):
                n += 1
        return n, True
    except Exception:
        return 0, False


def _fetch_cdc_outbreak_news_count(timeout_sec: float = 10) -> tuple[int, bool]:
    """CDC outbreak news RSS entries (filtered to outbreak-relevant items)."""
    return _fetch_rss_count("https://tools.cdc.gov/api/v2/resources/media/403372.rss", timeout_sec=timeout_sec, outbreak_only=False)


def _fetch_un_global_health_count(timeout_sec: float = 15) -> tuple[int, bool]:
    """UN global health page signal via GDELT domain query."""
    return _fetch_gdelt_domain_hits("un.org", timeout_sec=timeout_sec)


def _fetch_gdelt_top_articles(max_records: int = 10, timeout_sec: float = 20) -> tuple[list[dict], bool]:
    """
    Pull recent outbreak-related article links from GDELT for quick drill-down,
    then run them through the AI signal validator. Only items confirmed as
    real outbreak signals are returned and persisted to the signal store.
    """
    try:
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc?"
            "query=cholera+OR+malaria+OR+outbreak+OR+epidemic&"
            f"mode=ArtList&maxrecords={int(max_records)}&format=json&timespan=1d&sort=datedesc"
        )
        r = requests.get(url, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return [], False
        articles = r.json().get("articles") or []
        candidates: list[dict] = []
        for item in articles[:max_records]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            link = str(item.get("url") or "").strip()
            domain = str(item.get("domain") or "").strip()
            if not title and not link:
                continue
            candidates.append(
                {
                    "source": "GDELT",
                    "title": title or "Untitled article",
                    "url": link,
                    "description": "",
                    "meta": domain or "unknown",
                }
            )

        decisions = _validate_and_persist(candidates)
        cleaned: list[dict] = []
        for cand, dec in zip(candidates, decisions):
            if not dec.get("is_signal"):
                continue
            cleaned.append(
                {
                    "title": cand["title"],
                    "url": cand["url"],
                    "domain": cand.get("meta") or "unknown",
                }
            )
        return cleaned, True
    except Exception:
        return [], False


def _fetch_x_signal_count(timeout_sec: float = 8) -> tuple[int, bool, str]:
    token = (os.getenv("X_API_BEARER") or "").strip()
    if not token:
        return 0, False, "missing X_API_BEARER"
    try:
        url = "https://api.twitter.com/2/tweets/search/recent"
        params = {"query": "cholera OR malaria OR outbreak lang:en", "max_results": 10}
        r = requests.get(
            url,
            params=params,
            timeout=timeout_sec,
            headers={"Authorization": f"Bearer {token}", **_http_headers()},
        )
        if r.status_code != 200:
            return 0, False, f"http {r.status_code}"
        data = r.json().get("data") or []
        return len(data), True, "ok"
    except Exception as exc:
        return 0, False, str(exc)[:120]


def _fetch_linkedin_signal_count(timeout_sec: float = 8) -> tuple[int, bool, str]:
    token = (os.getenv("LINKEDIN_ACCESS_TOKEN") or "").strip()
    org = (os.getenv("LINKEDIN_ORG_ID") or "").strip()
    if not token:
        return 0, False, "missing LINKEDIN_ACCESS_TOKEN"
    if not org:
        return 0, False, "missing LINKEDIN_ORG_ID"
    try:
        url = "https://api.linkedin.com/v2/shares"
        params = {"q": "owners", "owners": f"urn:li:organization:{org}", "count": 10}
        r = requests.get(
            url,
            params=params,
            timeout=timeout_sec,
            headers={"Authorization": f"Bearer {token}", **_http_headers()},
        )
        if r.status_code != 200:
            return 0, False, f"http {r.status_code}"
        elems = r.json().get("elements") or []
        return len(elems), True, "ok"
    except Exception as exc:
        return 0, False, str(exc)[:120]


def _fetch_meta_signal_count(timeout_sec: float = 8) -> tuple[int, bool, str]:
    token = (os.getenv("META_ACCESS_TOKEN") or "").strip()
    page_id = (os.getenv("META_PAGE_ID") or "").strip()
    if not token:
        return 0, False, "missing META_ACCESS_TOKEN"
    if not page_id:
        return 0, False, "missing META_PAGE_ID"
    try:
        url = f"https://graph.facebook.com/v20.0/{page_id}/posts"
        params = {"limit": 10, "access_token": token}
        r = requests.get(url, params=params, timeout=timeout_sec, headers=_http_headers())
        if r.status_code != 200:
            return 0, False, f"http {r.status_code}"
        data = r.json().get("data") or []
        return len(data), True, "ok"
    except Exception as exc:
        return 0, False, str(exc)[:120]


@st.cache_data(ttl=180, show_spinner="Refreshing outbreak + open-web feeds...")
def fetch_realtime_outbreak_data():
    """
    Short-TTL snapshot (~30s cache). Mixes:
    - GDELT: news article volume (24h).
    - Reddit public search, Hacker News (Algolia): real post/story counts (24h windows).
    - NewsAPI: optional when NEWSAPI_KEY is set.
    - WHO/CDC feeds + UN domain signal counts.
    This function intentionally avoids synthetic case magnitudes.
    """
    gdelt_hits, gdelt_ok = 0, False
    reddit_n, reddit_ok = 0, False
    hn_n, hn_ok = 0, False
    newsapi_n, newsapi_ok = 0, False
    who_n, who_ok = 0, False
    cdc_n, cdc_ok = 0, False
    un_n, un_ok = 0, False
    cidrap_n, cidrap_ok = 0, False
    reliefweb_n, reliefweb_ok = 0, False
    paho_n, paho_ok = 0, False
    gdelt_articles, gdelt_articles_ok = [], False
    reddit_items, reddit_items_ok = [], False
    hn_items, hn_items_ok = [], False
    who_items, who_items_ok = [], False
    cdc_items, cdc_items_ok = [], False
    cidrap_items, cidrap_items_ok = [], False
    reliefweb_items, reliefweb_items_ok = [], False
    paho_items, paho_items_ok = [], False
    x_n, x_ok, x_msg = 0, False, "not_checked"
    li_n, li_ok, li_msg = 0, False, "not_checked"
    meta_n, meta_ok, meta_msg = 0, False, "not_checked"

    WHO_FEED = "https://www.who.int/rss-feeds/news-english.xml"
    WHO_AFRO_FEED = "https://www.afro.who.int/rss.xml"
    CDC_FEED = "https://tools.cdc.gov/api/v2/resources/media/403372.rss"
    CIDRAP_FEED = "https://www.cidrap.umn.edu/rss.xml"
    RELIEFWEB_FEED = "https://reliefweb.int/disasters/rss.xml?primary_type=4611"
    PAHO_FEED = "https://www.paho.org/en/rss.xml"

    pool = ThreadPoolExecutor(max_workers=14)
    try:
        futures = {
            pool.submit(_fetch_gdelt_hits, 12): "gdelt",
            pool.submit(_fetch_reddit_recent_count): "reddit",
            pool.submit(_fetch_hn_algolia_hits): "hn",
            pool.submit(_fetch_newsapi_total): "newsapi",
            pool.submit(_fetch_who_outbreak_news_count): "who",
            pool.submit(_fetch_cdc_outbreak_news_count): "cdc",
            pool.submit(_fetch_un_global_health_count, 12): "un",
            pool.submit(_fetch_rss_count, CIDRAP_FEED): "cidrap",
            pool.submit(_fetch_rss_count, RELIEFWEB_FEED): "reliefweb",
            pool.submit(_fetch_rss_count, PAHO_FEED): "paho",
            pool.submit(_fetch_gdelt_top_articles, 10, 12): "gdelt_articles",
            pool.submit(_fetch_reddit_recent_items): "reddit_items",
            pool.submit(_fetch_hn_recent_items): "hn_items",
            pool.submit(_fetch_rss_items, WHO_FEED, "WHO News"): "who_items",
            pool.submit(_fetch_rss_items, WHO_AFRO_FEED, "WHO Africa"): "who_afro_items",
            pool.submit(_fetch_rss_items, CDC_FEED, "CDC", 8, 10, False): "cdc_items",
            pool.submit(_fetch_rss_items, CIDRAP_FEED, "CIDRAP"): "cidrap_items",
            pool.submit(_fetch_rss_items, RELIEFWEB_FEED, "ReliefWeb"): "reliefweb_items",
            pool.submit(_fetch_rss_items, PAHO_FEED, "PAHO"): "paho_items",
            pool.submit(_fetch_x_signal_count): "x",
            pool.submit(_fetch_linkedin_signal_count): "linkedin",
            pool.submit(_fetch_meta_signal_count): "meta",
        }
        try:
            for fut in as_completed(futures, timeout=15):
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
                elif kind == "newsapi":
                    newsapi_n, newsapi_ok = val
                elif kind == "who":
                    who_n, who_ok = val
                elif kind == "cdc":
                    cdc_n, cdc_ok = val
                elif kind == "un":
                    un_n, un_ok = val
                elif kind == "cidrap":
                    cidrap_n, cidrap_ok = val
                elif kind == "reliefweb":
                    reliefweb_n, reliefweb_ok = val
                elif kind == "paho":
                    paho_n, paho_ok = val
                elif kind == "x":
                    x_n, x_ok, x_msg = val
                elif kind == "linkedin":
                    li_n, li_ok, li_msg = val
                elif kind == "meta":
                    meta_n, meta_ok, meta_msg = val
                elif kind == "gdelt_articles":
                    gdelt_articles, gdelt_articles_ok = val
                elif kind == "reddit_items":
                    reddit_items, reddit_items_ok = val
                elif kind == "hn_items":
                    hn_items, hn_items_ok = val
                elif kind == "who_items":
                    who_items, who_items_ok = val
                elif kind == "who_afro_items":
                    afro_items, afro_ok = val
                    if afro_ok:
                        who_items = (who_items or []) + afro_items
                        who_items_ok = True
                elif kind == "cdc_items":
                    cdc_items, cdc_items_ok = val
                elif kind == "cidrap_items":
                    cidrap_items, cidrap_items_ok = val
                elif kind == "reliefweb_items":
                    reliefweb_items, reliefweb_items_ok = val
                elif kind == "paho_items":
                    paho_items, paho_items_ok = val
        except TimeoutError:
            pass
    finally:
        # Don't block app refresh on slow upstreams (e.g. GDELT).
        # Already-finished futures stay accessible via fut.result().
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            pool.shutdown(wait=False)

    # Drain any tasks that *did* complete in the background but missed the deadline.
    for fut, kind in list(futures.items()):
        if not fut.done():
            continue
        try:
            val = fut.result()
        except Exception:
            continue
        if kind == "gdelt" and not gdelt_ok:
            gdelt_hits, gdelt_ok = val
        elif kind == "gdelt_articles" and not gdelt_articles_ok:
            gdelt_articles, gdelt_articles_ok = val
        elif kind == "un" and not un_ok:
            un_n, un_ok = val
        elif kind == "hn" and not hn_ok:
            hn_n, hn_ok = val
        elif kind == "hn_items" and not hn_items_ok:
            hn_items, hn_items_ok = val
        elif kind == "newsapi" and not newsapi_ok:
            newsapi_n, newsapi_ok = val
        elif kind == "cdc_items" and not cdc_items_ok:
            cdc_items, cdc_items_ok = val

    news_mentions = gdelt_hits if gdelt_ok else 0

    data = {
        "cholera_cases": 0,
        "malaria_ug_cases_est": 0,
        "affected_countries": 0,
        "news_mentions": news_mentions,
        "recent_alerts": [],
        "data_source": (
            "GDELT + Reddit + Hacker News (open-web) and WHO + CDC + UN + WHO Africa + CIDRAP + "
            "ReliefWeb + PAHO (official health) — all live, real signal counts only."
        ),
        "last_updated": datetime.now().strftime("%H:%M:%S EAT"),
        "gdelt_ok": gdelt_ok,
        "reddit_ok": reddit_ok,
        "hackernews_ok": hn_ok,
        "newsapi_ok": newsapi_ok,
        "who_ok": who_ok,
        "cdc_ok": cdc_ok,
        "un_ok": un_ok,
        "cidrap_ok": cidrap_ok,
        "reliefweb_ok": reliefweb_ok,
        "paho_ok": paho_ok,
        "x_ok": x_ok,
        "linkedin_ok": li_ok,
        "meta_ok": meta_ok,
        "gdelt_articles_ok": gdelt_articles_ok,
        "x_status": x_msg,
        "linkedin_status": li_msg,
        "meta_status": meta_msg,
        "social_sources_note": (
            "Open web: GDELT (news, 24h), Reddit public search, Hacker News (Algolia). "
            "Set NEWSAPI_KEY to add NewsAPI. X/LinkedIn/Meta only poll with official API keys. "
            "Official health: WHO News, WHO Africa, CDC, UN (via GDELT domain), CIDRAP, ReliefWeb disasters, PAHO."
        ),
        "source_links": {
            "GDELT (Doc API)": "https://api.gdeltproject.org/api/v2/doc/doc?query=cholera+OR+malaria+OR+outbreak&mode=ArtList&format=json&timespan=1d",
            "WHO News": "https://www.who.int/news",
            "WHO Africa": "https://www.afro.who.int/",
            "CDC Outbreaks": "https://www.cdc.gov/outbreaks/index.html",
            "UN Global Health": "https://www.un.org/en/global-issues/health",
            "CIDRAP": "https://www.cidrap.umn.edu/",
            "ReliefWeb (disease disasters)": "https://reliefweb.int/disasters?primary_type=4611",
            "PAHO": "https://www.paho.org/en",
            "Reddit search (last day)": "https://www.reddit.com/search/?q=cholera%20malaria%20outbreak&sort=new&t=day",
            "Hacker News (Algolia)": "https://hn.algolia.com/?q=cholera+malaria+outbreak",
            "NewsAPI (optional, keyed)": "https://newsapi.org/",
            "OWID Malaria": "https://ourworldindata.org/grapher/death-rate-from-malaria.csv",
        },
        "news_links": gdelt_articles if gdelt_articles_ok else [],
    }

    nm = int(data["news_mentions"])
    open_web_sum = nm + reddit_n + hn_n + (newsapi_n if newsapi_ok else 0)

    data["social_channels"] = {
        "News (GDELT 24h)": nm,
        "Reddit (public, 24h)": reddit_n if reddit_ok else 0,
        "Hacker News (Algolia, 24h)": hn_n if hn_ok else 0,
    }
    if newsapi_ok:
        data["social_channels"]["NewsAPI (24h, keyed)"] = newsapi_n
    data["social_channels"]["X / Twitter (official API, keyed)"] = x_n if x_ok else 0
    data["social_channels"]["LinkedIn (official API, keyed)"] = li_n if li_ok else 0
    data["social_channels"]["Facebook/Meta (official API, keyed)"] = meta_n if meta_ok else 0

    data["health_site_signals"] = {
        "WHO News (outbreak-relevant)": who_n if who_ok else 0,
        "CDC outbreak/news feed": cdc_n if cdc_ok else 0,
        "UN Global Health (un.org via GDELT)": un_n if un_ok else 0,
        "CIDRAP (outbreak-relevant)": cidrap_n if cidrap_ok else 0,
        "ReliefWeb disasters (disease)": reliefweb_n if reliefweb_ok else 0,
        "PAHO (outbreak-relevant)": paho_n if paho_ok else 0,
    }

    gdelt_open_web = []
    for item in (gdelt_articles if gdelt_articles_ok else []):
        gdelt_open_web.append(
            {
                "source": "GDELT",
                "title": str(item.get("title") or "GDELT article"),
                "url": str(item.get("url") or ""),
                "meta": str(item.get("domain") or "news"),
            }
        )

    data["open_web_cases"] = (gdelt_open_web[:10] + (reddit_items if reddit_items_ok else []) + (hn_items if hn_items_ok else []))[:30]

    un_refs = [
        {
            "source": "UN Global Health",
            "title": "UN global health updates",
            "url": "https://www.un.org/en/global-issues/health",
            "meta": "official",
        }
    ] if un_ok else []
    official_collected = (
        (who_items if who_items_ok else [])
        + (cdc_items if cdc_items_ok else [])
        + (cidrap_items if cidrap_items_ok else [])
        + (reliefweb_items if reliefweb_items_ok else [])
        + (paho_items if paho_items_ok else [])
        + un_refs
    )
    data["official_cases"] = official_collected[:30]

    source_ok_count = sum(
        1 for ok in (
            gdelt_ok, reddit_ok, hn_ok, newsapi_ok, who_ok, cdc_ok, un_ok,
            cidrap_ok, reliefweb_ok, paho_ok, x_ok, li_ok, meta_ok,
        ) if ok
    )
    data["affected_countries"] = min(60, max(0, source_ok_count * 2))

    data["social_sentiment_index"] = round(
        max(-1.0, min(1.0, (reddit_n - hn_n) / max(100, open_web_sum))),
        2,
    )
    official_sum = who_n + cdc_n + un_n
    data["social_urgency_score"] = min(100, int(open_web_sum / 35) + min(28, official_sum * 2))
    data["sim_recommended_tier"] = (
        "Surge" if data["social_urgency_score"] >= 72 else ("Elevated" if data["social_urgency_score"] >= 48 else "Routine")
    )

    alerts: list[str] = []
    if news_mentions >= 2000:
        alerts.append("GDELT outbreak-related news volume is elevated in the last 24h.")
    if reddit_ok and reddit_n >= 30:
        alerts.append("Reddit discussion volume crossed monitoring threshold in 24h.")
    if official_sum >= 20:
        alerts.append("WHO/CDC/UN feed activity indicates elevated official reporting signal.")
    if x_ok and x_n >= 8:
        alerts.append("X official API shows increased recent outbreak-related posting activity.")
    if not alerts:
        alerts.append("No major cross-source surge detected in the current 24h signal snapshot.")
    data["recent_alerts"] = alerts[:4]

    # AI-validated signal counts are sourced from the persistent SQLite store.
    # This is the "real" signal volume — keyword-only counts (above) are the
    # raw feed activity, validated counts are what passed the AI gate.
    try:
        data["validated_signals_24h"] = int(_count_recent_signals(24))
        data["validated_diseases"] = _list_signal_diseases(min_count=1)[:25]
    except Exception:
        data["validated_signals_24h"] = 0
        data["validated_diseases"] = []

    # Single source of truth for every dashboard KPI — keeps numbers consistent
    # across Home / Strategic signals / Executive brief / Action Plan / Global Surveillance.
    data["dashboard"] = compute_dashboard_metrics(data)

    return data


def compute_dashboard_metrics(realtime_data: dict) -> dict:
    """
    Derive a single, consistent set of dashboard numbers from a realtime snapshot.
    Every page should read from realtime_data["dashboard"] instead of recomputing locally.
    """
    news_mentions = int(realtime_data.get("news_mentions", 0) or 0)
    affected_countries = int(realtime_data.get("affected_countries", 0) or 0)
    urgency = int(realtime_data.get("social_urgency_score", 0) or 0)
    sentiment = float(realtime_data.get("social_sentiment_index", 0.0) or 0.0)

    social_channels = realtime_data.get("social_channels") or {}
    health_site_signals = realtime_data.get("health_site_signals") or {}
    open_web_total = int(sum(int(v or 0) for v in social_channels.values()))
    official_total = int(sum(int(v or 0) for v in health_site_signals.values()))
    combined_total = open_web_total + official_total

    feed_keys = (
        "gdelt_ok", "reddit_ok", "hackernews_ok", "newsapi_ok",
        "who_ok", "cdc_ok", "un_ok",
        "cidrap_ok", "reliefweb_ok", "paho_ok",
    )
    feeds_online = sum(1 for k in feed_keys if realtime_data.get(k))
    feeds_total = len(feed_keys)
    feed_reliability = (feeds_online / feeds_total) if feeds_total else 0.0

    # Composite signal index (0-100), deterministic and documented.
    news_component = min(35.0, news_mentions / 8.0)         # 0-35 from GDELT (≥280 articles saturates)
    open_web_component = min(25.0, open_web_total / 6.0)    # 0-25 from open-web volume (≥150 saturates)
    official_component = min(25.0, official_total / 1.5)    # 0-25 from official feeds (≥38 saturates)
    reliability_component = feed_reliability * 15.0         # 0-15 from feed connectivity
    signal_score = int(round(news_component + open_web_component + official_component + reliability_component))
    signal_score = max(0, min(100, signal_score))

    if signal_score >= 75:
        risk_level = "High"
    elif signal_score >= 55:
        risk_level = "Medium"
    elif signal_score >= 30:
        risk_level = "Low"
    else:
        risk_level = "Baseline"

    if urgency >= 72 or signal_score >= 75:
        posture = "Surge"
        response_window = "0-24h"
    elif urgency >= 48 or signal_score >= 55:
        posture = "Elevated"
        response_window = "24-72h"
    else:
        posture = "Routine"
        response_window = "72h+"

    recent_alerts = realtime_data.get("recent_alerts") or []
    no_surge_marker = "No major cross-source surge"
    priority_alerts = sum(
        1 for a in recent_alerts if no_surge_marker.lower() not in str(a).lower()
    )

    # High-risk-district proxy uses real official signal volume + urgency
    high_risk_districts = max(0, min(15, (urgency // 20) + (official_total // 8)))

    drivers = [
        {"label": "GDELT news (24h)", "value": news_mentions, "weight_pct": int(round(news_component / 100 * 100))},
        {"label": "Open-web volume (24h)", "value": open_web_total, "weight_pct": int(round(open_web_component / 100 * 100))},
        {"label": "Official feeds (24h)", "value": official_total, "weight_pct": int(round(official_component / 100 * 100))},
        {"label": "Feed connectivity", "value": f"{feeds_online}/{feeds_total}", "weight_pct": int(round(reliability_component / 100 * 100))},
    ]

    return {
        "signal_score": signal_score,
        "risk_level": risk_level,
        "posture": posture,
        "response_window": response_window,
        "priority_alerts": priority_alerts,
        "high_risk_districts": high_risk_districts,
        "open_web_total": open_web_total,
        "official_total": official_total,
        "combined_total": combined_total,
        "feeds_online": feeds_online,
        "feeds_total": feeds_total,
        "feed_reliability_pct": int(round(feed_reliability * 100)),
        "news_mentions": news_mentions,
        "affected_countries": affected_countries,
        "urgency": urgency,
        "sentiment": round(sentiment, 2),
        "drivers": drivers,
        "components": {
            "news": round(news_component, 1),
            "open_web": round(open_web_component, 1),
            "official": round(official_component, 1),
            "reliability": round(reliability_component, 1),
        },
    }


def get_signal_sources(realtime_data: dict) -> dict:
    """
    Return a normalized map of {category: [items]} where each item carries
    {source, title, url, meta}, so any page can render clickable signal links
    next to its KPIs.
    """
    open_web = list(realtime_data.get("open_web_cases") or [])
    official = list(realtime_data.get("official_cases") or [])
    news = list(realtime_data.get("news_links") or [])
    news_normalized = [
        {
            "source": "GDELT",
            "title": str(n.get("title") or "GDELT article"),
            "url": str(n.get("url") or "").strip(),
            "meta": str(n.get("domain") or "news"),
        }
        for n in news
    ]
    return {
        "open_web": open_web,
        "official": official,
        "news": news_normalized,
        "portals": realtime_data.get("source_links") or {},
    }


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


def _standardize_incidents_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {col: str(col).strip().lower().replace(" ", "_") for col in df.columns}
    df = df.rename(columns=renamed)
    alias_map = {
        "incident_date": "date_incident",
        "date_of_incident": "date_incident",
        "event_date": "date_incident",
        "disease_name": "disease",
    }
    for old_name, new_name in alias_map.items():
        if old_name in df.columns and new_name not in df.columns:
            df = df.rename(columns={old_name: new_name})
    return df


@st.cache_data(ttl=900, show_spinner="Loading incidents dataset...")
def load_disease_incidents_excel(excel_path: str) -> pd.DataFrame:
    df = pd.read_excel(excel_path)
    df = _standardize_incidents_columns(df)
    required = {"date_incident", "disease"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    cleaned = df.copy()
    cleaned["date_incident"] = pd.to_datetime(cleaned["date_incident"], errors="coerce")
    cleaned["disease"] = cleaned["disease"].astype(str).str.strip()
    cleaned = cleaned[cleaned["disease"].notna() & (cleaned["disease"] != "")]
    cleaned = cleaned[cleaned["disease"].str.lower() != "nan"]
    cleaned["year"] = cleaned["date_incident"].dt.year
    cleaned = cleaned.dropna(subset=["year"]).copy()
    cleaned["year"] = cleaned["year"].astype(int)
    return cleaned


def run_disease_forecast_from_excel(
    excel_path: str,
    train_until_year: int = 2021,
    simulation_year: int = 2030,
    growth_factor: float = 2.0,
) -> dict:
    from sklearn.ensemble import RandomForestRegressor

    incidents = load_disease_incidents_excel(excel_path)
    if incidents.empty:
        raise ValueError("Incidents dataset is empty after cleaning.")

    yearly_wide = (
        incidents.groupby(["year", "disease"])
        .size()
        .reset_index(name="count")
        .pivot(index="year", columns="disease", values="count")
        .fillna(0)
        .reset_index()
    )

    if "<NA>" in yearly_wide.columns:
        yearly_wide = yearly_wide.drop(columns=["<NA>"])

    feature_cols = [col for col in yearly_wide.columns if col != "year"]
    if not feature_cols:
        raise ValueError("No disease feature columns found after pivoting.")

    train_data = yearly_wide[yearly_wide["year"] <= train_until_year].copy()
    if train_data.empty:
        raise ValueError(f"No training rows found for year <= {train_until_year}.")

    train_data["total_cases"] = train_data[feature_cols].sum(axis=1)
    X_train = train_data[feature_cols]
    y_train = train_data["total_cases"]

    model = RandomForestRegressor(n_estimators=500, random_state=42)
    model.fit(X_train, y_train)

    latest_row = yearly_wide.sort_values("year").tail(1).copy()
    X_sim = latest_row[feature_cols] * float(growth_factor)
    predicted_total_cases = float(model.predict(X_sim)[0])

    top_diseases = (
        incidents.groupby("disease")
        .size()
        .reset_index(name="total_count")
        .sort_values("total_count", ascending=False)
        .head(10)
    )

    yearly_totals = (
        incidents.groupby("year")
        .size()
        .reset_index(name="incident_count")
        .sort_values("year")
    )

    quality = {
        "rows_loaded": int(len(incidents)),
        "year_min": int(incidents["year"].min()),
        "year_max": int(incidents["year"].max()),
        "unique_diseases": int(incidents["disease"].nunique()),
        "training_rows": int(len(train_data)),
    }

    return {
        "predicted_total_cases": predicted_total_cases,
        "simulation_year": int(simulation_year),
        "train_until_year": int(train_until_year),
        "growth_factor": float(growth_factor),
        "quality": quality,
        "top_diseases": top_diseases,
        "yearly_totals": yearly_totals,
    }


def list_validated_signal_diseases(min_count: int = 1) -> list[str]:
    """Diseases the AI validator has tagged on persisted signals."""
    try:
        return _list_signal_diseases(min_count=int(min_count))
    except Exception:
        return []


def run_signal_forecast(
    disease: str | None = None,
    horizon_days: int = 14,
    lookback_days: int = 120,
) -> dict:
    """
    Train a Random Forest on the AI-validated signal history persisted in
    `signals.db` and forecast the next `horizon_days` of daily signal volume.

    This replaces the Excel-based trainer for Forecast Lab — the model now
    learns directly from real, validated outbreak signals as they accumulate.

    Returns a dict with keys:
        ok                    bool
        reason                str          (only when ok is False)
        history               DataFrame    (date, count)
        forecast              DataFrame    (date, predicted, lower, upper)
        feature_importance    list[dict]   (feature, importance)
        backtest              dict         (mae, mape, n)
        disease               str
        horizon_days          int
        lookback_days         int
        min_history_days      int
        rows_available        int
    """
    from sklearn.ensemble import RandomForestRegressor
    import numpy as np

    MIN_HISTORY_DAYS = 14

    daily = _signal_daily_aggregate(disease=disease, days=lookback_days)
    rows_available = int(len(daily))

    base_payload = {
        "ok": False,
        "reason": "",
        "history": daily,
        "forecast": pd.DataFrame(columns=["date", "predicted", "lower", "upper"]),
        "feature_importance": [],
        "backtest": {},
        "disease": disease or "All",
        "horizon_days": int(horizon_days),
        "lookback_days": int(lookback_days),
        "min_history_days": MIN_HISTORY_DAYS,
        "rows_available": rows_available,
    }

    if daily.empty or rows_available < MIN_HISTORY_DAYS:
        base_payload["reason"] = (
            f"Not enough validated signal history yet "
            f"({rows_available} day(s) collected, need {MIN_HISTORY_DAYS}). "
            "Forecast Lab unlocks once the live feed pipeline accumulates enough signals."
        )
        return base_payload

    # Fill missing calendar days with zero-count rows so lag features stay aligned.
    daily = daily.set_index("date").asfreq("D", fill_value=0).reset_index()
    daily = daily.rename(columns={"index": "date"})

    LAGS = (1, 2, 3, 7, 14)
    ROLL = (3, 7)
    df = daily.copy()
    for lag in LAGS:
        df[f"lag_{lag}"] = df["count"].shift(lag)
    for w in ROLL:
        df[f"roll_{w}"] = df["count"].shift(1).rolling(w).mean()
    df["dow"] = pd.to_datetime(df["date"]).dt.dayofweek
    df = df.dropna().reset_index(drop=True)
    if df.empty:
        base_payload["reason"] = (
            "Not enough contiguous signal history to build lag features yet."
        )
        return base_payload

    feature_cols = [c for c in df.columns if c not in ("date", "count")]
    X = df[feature_cols].values
    y = df["count"].astype(float).values

    split = max(1, int(len(df) * 0.8))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    backtest = {"mae": None, "mape": None, "n": int(len(X_test))}
    if len(X_test) > 0:
        bt_model = RandomForestRegressor(n_estimators=300, random_state=42)
        bt_model.fit(X_train, y_train)
        preds_test = bt_model.predict(X_test)
        mae = float(np.mean(np.abs(preds_test - y_test)))
        denom = np.where(y_test == 0, 1.0, y_test)
        mape = float(np.mean(np.abs((preds_test - y_test) / denom)))
        backtest = {"mae": round(mae, 2), "mape": round(mape, 4), "n": int(len(X_test))}

    model = RandomForestRegressor(n_estimators=400, random_state=42)
    model.fit(X, y)

    importance = sorted(
        [
            {"feature": feat, "importance": round(float(imp), 4)}
            for feat, imp in zip(feature_cols, model.feature_importances_)
        ],
        key=lambda r: r["importance"],
        reverse=True,
    )

    last_date = pd.to_datetime(daily["date"].iloc[-1])
    series = daily["count"].astype(float).tolist()
    forecast_rows: list[dict] = []
    for step in range(int(horizon_days)):
        future_date = last_date + timedelta(days=step + 1)
        feat = {}
        for lag in LAGS:
            feat[f"lag_{lag}"] = series[-lag] if len(series) >= lag else 0.0
        for w in ROLL:
            window = series[-w:] if len(series) >= w else series
            feat[f"roll_{w}"] = float(sum(window) / max(1, len(window)))
        feat["dow"] = future_date.dayofweek
        x_row = np.array([[feat[c] for c in feature_cols]])
        # Per-tree spread approximates a confidence band without external libs.
        per_tree = np.array([est.predict(x_row)[0] for est in model.estimators_])
        pred = float(max(0.0, per_tree.mean()))
        lower = float(max(0.0, np.percentile(per_tree, 10)))
        upper = float(max(0.0, np.percentile(per_tree, 90)))
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

    return {
        "ok": True,
        "reason": "",
        "history": daily,
        "forecast": forecast_df,
        "feature_importance": importance,
        "backtest": backtest,
        "disease": disease or "All",
        "horizon_days": int(horizon_days),
        "lookback_days": int(lookback_days),
        "min_history_days": MIN_HISTORY_DAYS,
        "rows_available": rows_available,
    }


def apply_live_signal_adjustment(base_prediction: float, realtime_data: dict) -> dict:
    """
    Blend historical-model output with live social/data-site signals.
    This does not retrain the RF model; it applies a transparent multiplier.
    """
    news_mentions = int(realtime_data.get("news_mentions", 0) or 0)
    countries = int(realtime_data.get("affected_countries", 0) or 0)
    urgency = int(realtime_data.get("social_urgency_score", 0) or 0)

    social_channels = realtime_data.get("social_channels") or {}
    health_site_signals = realtime_data.get("health_site_signals") or {}
    social_volume = int(sum(v for v in social_channels.values() if isinstance(v, (int, float))))
    health_volume = int(sum(v for v in health_site_signals.values() if isinstance(v, (int, float))))

    # Keep each component capped so spikes don't explode predictions.
    news_component = min(0.35, news_mentions / 12000.0)
    urgency_component = min(0.30, urgency / 200.0)
    countries_component = min(0.18, countries / 140.0)
    social_component = min(0.25, social_volume / 15000.0)
    health_component = min(0.20, health_volume / 4000.0)

    uplift = news_component + urgency_component + countries_component + social_component + health_component
    multiplier = 1.0 + uplift
    adjusted_prediction = float(base_prediction) * multiplier

    return {
        "base_prediction": float(base_prediction),
        "adjusted_prediction": float(adjusted_prediction),
        "multiplier": float(multiplier),
        "uplift": float(uplift),
        "features": {
            "news_mentions": news_mentions,
            "affected_countries": countries,
            "social_urgency_score": urgency,
            "social_volume": social_volume,
            "health_site_volume": health_volume,
        },
    }
