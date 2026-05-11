"""
Free, attributable web context for **Coolio world briefing** (no paid search API):

- Wikipedia (MediaWiki API, introductory plain-text extract + page URL)
- WHO news RSS (English) — titles/links mentioning the disease keywords
- OWID live snapshot sentence when the disease is COVID-like (reuse coolio_owid)

This is **not** exhaustive global surveillance; it grounds the LLM in a few
fresh, citable lines instead of pure hallucination.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

import requests

from .coolio_owid import disease_uses_owid_covid, get_owid_live_snapshot

_DEFAULT_UA = (
    "PathogenEconomyEpiforecast/1.0 (Coolio world context; "
    "https://github.com) requests"
)


def _http_get(url: str, *, params: dict[str, Any] | None = None, timeout: float = 14) -> requests.Response | None:
    try:
        r = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": _DEFAULT_UA},
        )
        return r if r.status_code == 200 else None
    except Exception:
        return None


def wikipedia_context(disease: str) -> dict[str, Any]:
    """Return {ok, title, extract, url} for best-effort Wikipedia grounding."""
    q = (disease or "").strip()
    out: dict[str, Any] = {"ok": False, "title": "", "extract": "", "url": ""}
    if len(q) < 2:
        return out
    base = "https://en.wikipedia.org/w/api.php"
    r = _http_get(
        base,
        params={
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "titles": q,
        },
    )
    extract = ""
    title = ""
    page_url = ""
    if r is not None:
        try:
            pages = (r.json().get("query") or {}).get("pages") or {}
            for _pid, pdata in pages.items():
                if str(_pid) == "-1":
                    continue
                title = str(pdata.get("title") or q)
                extract = str(pdata.get("extract") or "").strip()
                if title:
                    page_url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                break
        except Exception:
            pass
    if not extract:
        sr = _http_get(
            base,
            params={"action": "query", "format": "json", "list": "search", "srsearch": q, "srlimit": 1},
        )
        if sr is not None:
            try:
                hits = (sr.json().get("query") or {}).get("search") or []
                if hits:
                    title = str(hits[0].get("title") or "")
                    if title:
                        r2 = _http_get(
                            base,
                            params={
                                "action": "query",
                                "format": "json",
                                "prop": "extracts",
                                "exintro": 1,
                                "explaintext": 1,
                                "titles": title,
                            },
                        )
                        if r2 is not None:
                            pages = (r2.json().get("query") or {}).get("pages") or {}
                            for _pid, pdata in pages.items():
                                extract = str(pdata.get("extract") or "").strip()
                                page_url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                                break
            except Exception:
                pass
    extract = re.sub(r"\s+", " ", extract).strip()
    if len(extract) > 1200:
        extract = extract[:1197] + "…"
    if extract or page_url:
        out.update({"ok": True, "title": title or q, "extract": extract, "url": page_url})
    return out


def who_news_matches(disease: str, *, max_items: int = 10) -> list[dict[str, str]]:
    """Recent WHO news RSS rows whose title/description mentions disease tokens."""
    label = (disease or "").strip()
    if len(label) < 2:
        return []
    tokens = [t for t in re.split(r"[^\w]+", label.casefold()) if len(t) >= 3]
    if not tokens:
        tokens = [label.casefold()]
    url = "https://www.who.int/rss-feeds/news-english.xml"
    r = _http_get(url, timeout=16)
    if r is None or not r.text.strip():
        return []
    out: list[dict[str, str]] = []
    try:
        root = ET.fromstring(r.text)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            blob = f"{title} {desc}".casefold()
            if not any(t in blob for t in tokens):
                continue
            out.append({"publisher": "WHO News", "title": title or "WHO item", "url": link})
            if len(out) >= max_items:
                break
    except Exception:
        return []
    return out


def owid_context_line(disease: str | None) -> str:
    if not disease_uses_owid_covid(disease):
        return ""
    snap = get_owid_live_snapshot(iso_code="UGA")
    if not snap.get("ok"):
        return ""
    return (
        f"OWID COVID (Uganda) latest row {snap.get('last_date')}: "
        f"smoothed new cases/day {float(snap.get('new_cases_smoothed') or 0):.1f}; "
        f"stringency {float(snap.get('stringency_index') or 0):.1f}."
    )


def build_world_context_pack(disease: str | None) -> dict[str, Any]:
    d = (disease or "All diseases").strip() or "All diseases"
    wiki = wikipedia_context(d) if d.lower() not in ("all diseases", "all") else {"ok": False}
    who = who_news_matches(d) if d.lower() not in ("all diseases", "all") else []
    owid = owid_context_line(disease) if disease else ""
    sources: list[dict[str, str]] = []
    for w in who:
        sources.append({"publisher": w["publisher"], "title": w["title"], "url": w["url"]})
    if wiki.get("ok") and wiki.get("url"):
        sources.append(
            {
                "publisher": "Wikipedia",
                "title": wiki.get("title") or d,
                "url": str(wiki.get("url")),
            }
        )
    lines: list[str] = []
    if wiki.get("ok") and wiki.get("extract"):
        lines.append(f"Wikipedia ({wiki.get('title')}): {wiki.get('extract')}")
    if who:
        lines.append("WHO English news headlines (keyword match):")
        for w in who[:6]:
            lines.append(f"  - {w['title']}")
    if owid:
        lines.append(owid)
    return {
        "disease_focus": d,
        "prompt_block": "\n".join(lines).strip() or "(No matching open-web snippets for this focus in this fetch.)",
        "sources": sources[:24],
        "wikipedia": wiki,
        "who_hits": who,
    }
