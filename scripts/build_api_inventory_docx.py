"""
Build STI-EPI-FORECAST_API_Inventory.docx using only Python standard library.
"""
from __future__ import annotations

import html
import zipfile
from datetime import date
from pathlib import Path


def _p(text: str, bold: bool = False) -> str:
    esc = html.escape(text, quote=False)
    b = "<w:b/>" if bold else ""
    return f'<w:p><w:r><w:rPr>{b}</w:rPr><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'


def _build_document_xml(sections: list[tuple[str, list[str]]]) -> str:
    parts: list[str] = []
    parts.append(_p("STI-EPI-FORECAST - API Inventory and Access Guide", bold=True))
    parts.append(_p(f"Generated: {date.today().isoformat()}"))
    parts.append(_p(""))
    parts.append(
        _p(
            "Purpose: list all APIs for this app, explain what each API does, how to get access, and how each helps your public-health workflow.",
        )
    )
    parts.append(_p(""))
    for title, lines in sections:
        parts.append(_p(title, bold=True))
        for line in lines:
            parts.append(_p(line))
        parts.append(_p(""))
    body = "".join(parts)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>"""


def write_docx(out_path: Path, sections: list[tuple[str, list[str]]]) -> None:
    document_xml = _build_document_xml(sections)
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""
    core_props = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>STI-EPI-FORECAST API Inventory</dc:title>
  <dc:creator>STI-EPI-FORECAST</dc:creator>
  <cp:lastModifiedBy>Build script</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{date.today().isoformat()}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{date.today().isoformat()}</dcterms:modified>
</cp:coreProperties>"""
    app_props = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>STI-EPI-FORECAST</Application>
</Properties>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("docProps/core.xml", core_props)
        zf.writestr("docProps/app.xml", app_props)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "STI-EPI-FORECAST_API_Inventory.docx"
    sections: list[tuple[str, list[str]]] = [
        (
            "1. Internal APIs (already in this project)",
            [
                "GET /health - What it does: uptime check. How to get it: included in your FastAPI server. How it helps: monitoring and load balancer health checks.",
                "GET /v1/catalog/public-apis - What it does: returns suggested third-party APIs. How to get it: included in your FastAPI server. How it helps: quick integration planning.",
                "GET /v1/models - What it does: returns default configured LLM model. How to get it: included in your FastAPI server. How it helps: model diagnostics and UI model display.",
                "POST /v1/nlp-alerts - What it does: generates 4 surveillance alert lines (AI or fallback). How to get it: included in your FastAPI server; set AI key for live AI output. How it helps: concise decision-ready alerts in Global Surveillance.",
                "POST /v1/forecast/seir - What it does: returns SEIR projection time series. How to get it: included in your FastAPI server. How it helps: forecast curves for planning and intervention scenarios.",
                "POST /v1/chat/completions - What it does: OpenAI-compatible proxy endpoint. How to get it: included in your FastAPI server; configure CURSOR_API_KEY or AI_API_KEY and base URL. How it helps: unify AI provider calls behind one internal API.",
                "POST /v1/cursor/chat - What it does: convenience single-message chat endpoint. How to get it: included in your FastAPI server with same AI credentials. How it helps: simple internal testing and assistant-style use cases.",
            ],
        ),
        (
            "2. Health and outbreak data APIs (recommended external)",
            [
                "Our World in Data CSV (no key) - Get it: use public CSV URLs. Helps: historical malaria indicators and baseline trends.",
                "WHO GHO OData API (no key for many datasets) - Get it: use WHO OData docs/endpoints. Helps: official health indicators for policy and benchmarking.",
                "GDELT DOC API (no key) - Get it: public query API. Helps: near-real-time global media signals and event monitoring.",
                "NewsAPI (key required) - Get it: create account at newsapi.org, generate API key, store as NEWSAPI_KEY. Helps: structured news search and article metadata.",
            ],
        ),
        (
            "3. Social-media related APIs and reality check",
            [
                "Why you do not see full social-media APIs in your app now: many platforms heavily restrict public data access, require app review, and may be paid or compliance-gated.",
                "Current practical sources in your code: Reddit public JSON and Hacker News Algolia API. These are open-web discussion proxies, not full social-media firehoses.",
                "Reddit JSON (limited public) - Get it: public endpoints, optional OAuth for more advanced access. Helps: public sentiment and discussion trend signals.",
                "Hacker News Algolia (no key) - Get it: free public API. Helps: early technical/public discourse trend signals.",
                "X/Twitter, Facebook, Instagram, TikTok - Access note: generally limited/paid/restricted; requires official developer approval and strict terms. Helps if approved: richer real-time social signal volume and geotag clues.",
                "Recommendation: start with legal open-web signals (GDELT, NewsAPI, Reddit, HN), then add approved social APIs later under governance.",
            ],
        ),
        (
            "4. AI provider APIs (for NLP alerts and summaries)",
            [
                "OpenAI-compatible providers supported by your backend: OpenAI, xAI, Groq, OpenRouter.",
                "How to get them: create provider account, issue API key, set environment variables (CURSOR_API_KEY or AI_API_KEY, plus CURSOR_API_BASE_URL or AI_BASE_URL, optional model).",
                "How they help: produce narrative alerts, summaries, and policy-friendly text from structured outbreak signals.",
                "Fallback behavior: if key/provider is unavailable, your system still returns simulated fallback alerts so UI stays operational.",
            ],
        ),
        (
            "5. Setup checklist (how to get APIs working quickly)",
            [
                "Step 1: Run API server: python -m uvicorn api_server:app --host 0.0.0.0 --port 8000",
                "Step 2: Verify health: open http://localhost:8000/health",
                "Step 3: Add AI credentials as environment variables (one provider first).",
                "Step 4: Optional: add NEWSAPI_KEY for stronger media coverage.",
                "Step 5: Keep ALERTS_API_URL pointed to http://127.0.0.1:8000/v1/nlp-alerts (or your hosted URL).",
                "Step 6: Test from docs page: http://localhost:8000/docs",
            ],
        ),
        (
            "6. How these APIs help your mission",
            [
                "Early warning: ingest media/discussion signals before official case reports are complete.",
                "Faster decisions: convert noisy data into concise action alerts and risk trends.",
                "Planning support: run forecast scenarios for interventions, logistics, and surge readiness.",
                "Operational continuity: fallback paths keep dashboards useful even when one feed is down.",
                "Credibility: combine open-web velocity signals with official health datasets for balanced decisions.",
            ],
        ),
        (
            "7. Suggested next additions (after current baseline)",
            [
                "Add endpoint GET /v1/feeds/status for one-screen source health diagnostics.",
                "Add endpoint POST /v1/feeds/refresh for controlled remote cache refresh.",
                "Add endpoint GET /v1/outbreak/signals to standardize all feed outputs.",
                "Add endpoint POST /v1/alerts/subscribe for email/SMS/webhook delivery.",
            ],
        ),
    ]
    write_docx(out, sections)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
