"""
Build STI-EPI-FORECAST_GoLive_Paid_APIs_and_Features.docx using only Python stdlib.
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
    parts.append(_p("STI-EPI-FORECAST - Go-Live Paid APIs and Features Plan", bold=True))
    parts.append(_p(f"Generated: {date.today().isoformat()}"))
    parts.append(_p(""))
    parts.append(
        _p(
            "Objective: identify paid APIs, paid platform services, and paid implementation tasks that accelerate production go-live.",
        )
    )
    parts.append(
        _p(
            "PRICING NOTE: Indicative USD ranges for budgeting only. Vendor prices change; confirm with official quotes. FX applies for UGX settlement.",
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
  <dc:title>STI-EPI-FORECAST Go-Live Paid APIs and Features</dc:title>
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
    out = root / "STI-EPI-FORECAST_GoLive_Paid_APIs_and_Features.docx"
    sections: list[tuple[str, list[str]]] = [
        (
            "1. Paid APIs needed for fastest go-live (Priority A)",
            [
                "- LLM API (OpenAI, xAI, Groq, OpenRouter): NLP alerts, summaries, AI tables. | Usage: ~$50-500 USD/month light; $500-5,000 USD/month heavy.",
                "- NewsAPI paid plan: higher article limits and stability. | ~$80-450 USD/month (plan-dependent; verify NewsAPI site).",
                "- X API paid access: recent search for outbreak terms. | From roughly ~$100 USD/month entry paid tier historically—verify current X developer pricing.",
                "- LinkedIn commercial / partner APIs: org-level signals. | Often quote-based: ~$5,000-50,000+ USD/year for enterprise-style access when required.",
                "- Meta Graph API: page posts and insights. | Platform fees often $0 for standard limits; business verification time cost; marketing/partner tiers vary.",
                "- SMS/WhatsApp (Twilio, Infobip, MessageBird): alerts. | SMS ~$0.02-0.10 per message by route; WhatsApp conversation-based—request rate card.",
            ],
        ),
        (
            "2. Paid data and health intelligence sources (Priority A/B)",
            [
                "- Premium epidemiology or MoH/partner feeds (if licensed). | ~$500-50,000+ USD/year depending dataset and contract.",
                "- Commercial weather API (OpenWeather, Tomorrow.io, etc.). | ~$40-500 USD/month by call volume.",
                "- Commercial mobility or aggregated mobility indices (optional). | Often $200-2,000+ USD/month for research-grade access.",
                "- Managed analytics database / warehouse (BigQuery, Snowflake, Redshift). | ~$100-2,000 USD/month small-to-medium query volume.",
                "- Geocoding / places API (Google Maps, Mapbox). | ~$200-2,000 USD/month at moderate geocode volume; Mapbox often lower entry.",
            ],
        ),
        (
            "3. Paid cloud/platform services to reduce delivery time (Priority A)",
            [
                "- Managed cloud hosting (AWS/Azure/GCP/Render/Fly): Streamlit + FastAPI. | ~$40-250 USD/month small production footprint.",
                "- Managed PostgreSQL. | ~$25-150 USD/month small HA option higher.",
                "- Managed Redis / queue (Elasticache, Memorystore, etc.). | ~$15-80 USD/month.",
                "- Observability (Datadog, New Relic, Grafana Cloud). | ~$50-500 USD/month small team.",
                "- Secret vault (Secrets Manager, Key Vault). | ~$5-40 USD/month light usage.",
                "- CDN + WAF + DNS (Cloudflare Pro/Business, etc.). | ~$20-200 USD/month depending tier and rules.",
            ],
        ),
        (
            "4. Paid delivery features (work packages) to finish faster",
            [
                "- Authentication package (login, reset, sessions). | Contractor: ~$4,000-15,000 USD one-time OR SaaS IdP $200-800 USD/month.",
                "- RBAC package (roles, guards, admin UI). | ~$3,000-12,000 USD one-time.",
                "- API hardening (OpenAPI, validation, rate limits, errors). | ~$3,000-12,000 USD one-time.",
                "- Data quality package (retries, fallbacks, diagnostics). | ~$2,000-8,000 USD one-time.",
                "- Reporting package (exports, scheduled briefs). | ~$2,000-8,000 USD one-time.",
                "- Alerting package (email + SMS/WhatsApp + webhooks). | Build ~$2,000-10,000 USD one-time + messaging usage fees.",
                "- Security package (TLS hardening, rotation, audit logs, backups). | ~$3,000-15,000 USD one-time + recurring backup $5-40 USD/month.",
                "- DevOps package (CI/CD, staging/prod, rollback). | ~$3,000-12,000 USD one-time + CI minutes $0-300 USD/month.",
            ],
        ),
        (
            "4b. Optional procurement accelerators",
            [
                "- External penetration test before go-live. | ~$3,000-15,000 USD one-time.",
                "- External security or compliance consultant (health data). | ~$5,000-40,000 USD one-time depending scope.",
                "- Dedicated support / SLA from cloud vendor (Business support). | ~$100-1,000+ USD/month add-on.",
            ],
        ),
        (
            "5. What should be paid first (minimum spend sequence)",
            [
                "Step 1 (Week 1): Cloud hosting + managed DB + domain/SSL + observability.",
                "Step 2 (Week 1-2): LLM API + NewsAPI paid tier + email/SMS provider.",
                "Step 3 (Week 2): Authentication/RBAC/API hardening implementation.",
                "Step 4 (Week 2-3): Social connectors (X/LinkedIn/Meta) once credentials and approvals are granted.",
                "Step 5 (Week 3-4): Data quality and reporting automation + go-live readiness checks.",
            ],
        ),
        (
            "6. Dependencies and approvals required",
            [
                "- X/LinkedIn/Meta access depends on developer account approval and policy compliance.",
                "- WhatsApp production messaging usually needs verified sender templates and business approval.",
                "- Health/ministry data sharing may require formal MoU and data governance approvals.",
                "- Security and privacy sign-off should occur before production public rollout.",
            ],
        ),
        (
            "7. Go-live done criteria (paid roadmap complete)",
            [
                "- Core dashboard online with authenticated access and role controls.",
                "- At least one AI provider, one media API, and one alert channel fully operational.",
                "- Monitoring, backups, and uptime alerts active.",
                "- Social and health-site signal reports generated automatically.",
                "- Incident response and release rollback playbooks tested.",
            ],
        ),
        (
            "8. Indicative total cash planning bands (USD)",
            [
                "- Month 1 (setup + first month recurring): ~$500-3,000 USD if using paid infra + APIs lightly.",
                "- Steady-state monthly (small user base): ~$250-1,200 USD/month infra + tools + modest LLM/NewsAPI (excluding large SMS campaigns).",
                "- Implementation (one-time, contractor band): ~$35,000-150,000 USD full production hardening; smaller MVP slice ~$8,000-35,000 USD possible with reduced scope.",
                "- Add 15-25 percent contingency for FX and scope changes.",
            ],
        ),
    ]
    write_docx(out, sections)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
