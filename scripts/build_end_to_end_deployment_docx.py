"""
Build STI-EPI-FORECAST_End_to_End_Features_Deployment.docx using Python stdlib.
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
    parts.append(_p("STI-EPI-FORECAST - End-to-End Features and Deployment Blueprint", bold=True))
    parts.append(_p(f"Generated: {date.today().isoformat()}"))
    parts.append(_p(""))
    parts.append(
        _p(
            "This guide covers everything from initial build to public user deployment, including domain, security, operations, and go-live controls.",
        )
    )
    parts.append(
        _p(
            "PRICING NOTE: All amounts below are indicative USD ranges for budgeting only (2026-style ballparks). "
            "Actual vendor quotes vary by region, volume, contract, and FX. Obtain formal quotes before commitment.",
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
  <dc:title>STI-EPI-FORECAST End-to-End Deployment Blueprint</dc:title>
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
    out = root / "STI-EPI-FORECAST_End_to_End_Features_Deployment.docx"
    sections: list[tuple[str, list[str]]] = [
        (
            "1) Product scope and feature baseline",
            [
                "- Define user groups: national command, surveillance analyst, modeler, border ops, policy/investment, administrator. | Internal labour only; no direct SaaS fee.",
                "- Define modules: strategic signals, global surveillance, hotspots, disease profiler, forecast lab, action plan, executive brief, ROI/VDTEC, reports, admin. | Covered by dev budget.",
                "- Define outcomes: early warning, intervention guidance, procurement planning, ROI decisions, 7-1-7 impact estimation. | Covered by dev budget.",
            ],
        ),
        (
            "2) Functional features required before deployment",
            [
                "- Authentication (email/password initially), session handling, password reset. | Build: $4,000-15,000 USD one-time OR Auth0/Okta: ~$200-800 USD/month at small user counts.",
                "- Role-based access control (admin/analyst/viewer/developer). | Build: $3,000-12,000 USD one-time (often bundled with auth work).",
                "- Responsive UI across mobile/tablet/desktop and accessibility baseline. | Build: $2,000-8,000 USD one-time incremental.",
                "- Report generation and export (TXT/PDF/CSV) for leadership briefings. | Build: $2,000-6,000 USD one-time; storage pennies unless large PDF archives.",
                "- Alerting channels: email baseline, then SMS/WhatsApp/webhook. | Email SMTP often $0-25/month (SendGrid/Mailgun free tiers); SMS $0.02-0.10 per message region-dependent; WhatsApp Cloud API per conversation (vendor pricing).",
                "- Admin controls for sources, thresholds, users, and governance settings. | Build: $3,000-10,000 USD one-time.",
            ],
        ),
        (
            "3) Data and API integration features",
            [
                "- Core external signals: GDELT, Reddit public search, HN Algolia, optional NewsAPI. | GDELT/Reddit/HN: $0 API fee; NewsAPI Developer ~$80-450 USD/month (plan-dependent; verify current NewsAPI pricing).",
                "- Official health sources: WHO feed, CDC feed, UN global health signal monitoring; optional WHO GHO API. | Public feeds: $0; premium health data partners if any: $500-50,000+ USD/year depending dataset.",
                "- Social platform connectors: X, LinkedIn, Facebook/Meta via official API credentials. | X Basic access historically from ~$100 USD/month upward (tiers change—verify); LinkedIn/Meta often enterprise/contact sales (budget $0 if self-serve only, or $5,000-50,000+ USD/year for commercial tiers).",
                "- Forecast endpoint and NLP alert endpoint with retries, fallback, and diagnostics. | Included in hosting; LLM usage below.",
                "- Data validation, schema checks, source health status, and refresh scheduling. | Build: $2,000-8,000 USD one-time.",
                "- LLM usage (OpenAI / xAI / Groq / OpenRouter) for NLP alerts and AI tables. | Typical small deployment: $50-500 USD/month usage; heavier: $500-5,000+ USD/month.",
            ],
        ),
        (
            "4) Domain and public access setup (you asked for this explicitly)",
            [
                "- Buy domain (example: stiepiforecast.org) from a registrar. | ~$10-40 USD/year per domain (.com/.org typical).",
                "- Configure DNS records: A/AAAA or CNAME to your hosting target. | Often $0 (included with registrar or Cloudflare free DNS).",
                "- Add subdomains: app.<domain>, api.<domain>, admin.<domain> as needed. | $0 additional if DNS supports subdomains.",
                "- Configure SSL/TLS certificates (auto-renew via managed certs or Let's Encrypt). | $0 with Let's Encrypt or included with managed hosting / Cloudflare.",
                "- Enforce HTTPS redirect and HSTS for secure transport. | $0 (configuration).",
                "- Validate DNS propagation and certificate trust before launch. | $0 (labour).",
                "- Optional: Cloudflare Pro (WAF + better rules). | ~$20 USD/month (verify current Cloudflare pricing).",
            ],
        ),
        (
            "5) Cloud infrastructure and environments",
            [
                "- Provision cloud runtime for web app and API (container or managed app service). | Small always-on: ~$40-250 USD/month (single region, low traffic); scale adds cost.",
                "- Provision managed database (PostgreSQL recommended) and object storage for reports. | Managed Postgres small: ~$25-150 USD/month; object storage: ~$1-30 USD/month at modest volume.",
                "- Provision cache/queue service for background jobs and refresh pipelines. | Redis/managed queue: ~$15-80 USD/month small tier.",
                "- Separate environments: development, staging, production. | Multiply runtime+DB roughly 1.5-2.5x single-env cost (dev can be smaller): total ~$120-600 USD/month typical small three-env footprint.",
                "- Environment-specific secrets and configuration management. | AWS Secrets Manager ~$0.40/secret/month + API calls; Azure Key Vault similar order; or use platform env secrets at lower cost.",
            ],
        ),
        (
            "6) Security and compliance controls",
            [
                "- Secrets in vault only (no API keys in source code). | See secrets manager pricing above; labour to wire: $1,000-5,000 USD one-time.",
                "- API authentication and authorization (JWT/API keys, endpoint permissions). | Build: $3,000-12,000 USD one-time.",
                "- Encryption in transit (TLS) and at rest (database/storage). | Usually included in managed DB/storage; no extra if defaults used.",
                "- Audit logs for sensitive actions: login, config changes, exports, alerts. | Build + log storage: $1,000-6,000 USD one-time + ~$10-80 USD/month log retention small scale.",
                "- Backup policy, retention policy, and disaster recovery runbook. | Automated backups often $5-40 USD/month add-on; DR second region doubles infra roughly.",
                "- Privacy and governance policy for health and social signal data use. | Legal/consulting: $2,000-25,000 USD one-time depending jurisdiction and depth.",
            ],
        ),
        (
            "7) DevOps and release automation",
            [
                "- Git workflow with branch protection and PR review. | GitHub Team ~$4 USD/user/month; GitLab similar tiers.",
                "- CI pipeline: lint, unit tests, integration tests, security checks. | GitHub Actions minutes: often $0-50 USD/month small team; larger: $50-300 USD/month.",
                "- CD pipeline: deploy to staging then production with approval gate. | Included in CI minutes + labour: $2,000-10,000 USD one-time setup.",
                "- Automatic rollback strategy for failed release health checks. | Build: $1,000-5,000 USD one-time.",
                "- Versioned APIs (/v1 now, /v2 for non-breaking migration later). | Build: $1,000-4,000 USD one-time.",
            ],
        ),
        (
            "8) Observability and production operations",
            [
                "- Centralized logs for app, API, and background jobs. | Datadog small footprint often ~$100-400 USD/month; Sentry Team ~$26+ USD/month; cheaper stacks (Grafana Cloud) ~$50-200 USD/month.",
                "- Metrics and dashboards: latency, error rate, throughput, data freshness. | Bundled with observability vendor above.",
                "- Uptime and synthetic checks for app URL and API endpoints. | Pingdom/UptimeRobot ~$7-80 USD/month depending checks; or included in Datadog synthetics (higher tier).",
                "- Alert rules for source failures, auth failures, and high error rates. | Configuration labour: $500-3,000 USD one-time.",
                "- On-call rotation and incident response playbooks. | Process design: internal; optional PagerDuty ~$19+ USD/user/month.",
            ],
        ),
        (
            "9) Testing and go-live quality gates",
            [
                "- Unit tests for data services, risk scoring, and API payload validation. | Build: $3,000-12,000 USD one-time.",
                "- Integration tests for source connectors and fallback pathways. | Build: $3,000-10,000 USD one-time.",
                "- End-to-end smoke tests for login, dashboard render, report download, and admin checks. | Build: $2,000-8,000 USD one-time.",
                "- Load/performance tests for peak usage and report generation. | Tools (k6 cloud) ~$0-100 USD/month short campaigns; services labour $2,000-8,000 USD one-time.",
                "- UAT signoff with real user workflows before production cutover. | Internal labour; external QA firm optional $5,000-30,000 USD one-time.",
            ],
        ),
        (
            "10) End-user deployment and adoption",
            [
                "- Publish user URL (domain) and API URL with stable documentation. | Domain cost above; docs hosting $0 (in repo) or portal $0-50 USD/month.",
                "- Create user onboarding packs: quick-start, role-based workflow guides, FAQ. | Technical writing: $1,500-8,000 USD one-time or internal.",
                "- Configure support channels and ticket escalation process. | Zendesk/Freshdesk ~$50-150 USD/agent/month or free tier for small teams.",
                "- Train leadership and operations teams on interpretation of mixed real/simulated indicators. | Training delivery: internal; external workshop $2,000-15,000 USD per cohort.",
                "- Schedule weekly release cycle and monthly model/data review cycle. | $0 process.",
            ],
        ),
        (
            "11) Fast-track execution plan (small time delivery)",
            [
                "- Week 1: Domain + DNS + SSL + cloud infra + CI/CD baseline + auth. | Cash outlay often ~$150-800 USD first month infra + domain + basic observability.",
                "- Week 2: API hardening + role controls + monitoring + backup setup. | Infra recurring as above; labour is main cost.",
                "- Week 3: Social connector approvals + report automation + alert channels. | API fees as in section 3; SMS budget separately.",
                "- Week 4: UAT, load test, security review, production launch. | Optional external pen test $3,000-15,000 USD one-time.",
            ],
        ),
        (
            "12) Final go-live checklist",
            [
                "- Domain resolves correctly and SSL is valid on all public endpoints.",
                "- App and API health checks are green for 72 hours continuously.",
                "- Backup restore drill completed successfully.",
                "- Security review complete and secrets rotation policy active.",
                "- Core reports and alerts tested with real recipients.",
                "- Governance signoff completed for operational rollout.",
            ],
        ),
        (
            "13) Consolidated indicative budget (two views)",
            [
                "A) Recurring monthly (small production footprint, rough band): $250-1,200 USD/month = domain/DNS + small cloud (app+API) + managed DB + cache + basic observability + CI + modest LLM/NewsAPI usage.",
                "B) One-time implementation (external team or contractor band): $35,000-150,000 USD = auth/RBAC, hardening, tests, reporting, integrations, training, security review—highly variable by scope and location.",
                "C) Annual third-party API and data (excluding infra): $1,000-25,000+ USD/year = NewsAPI + X/LinkedIn tiers + optional datasets; LLM often counted monthly not annual.",
                "D) Contingency: add 15-25 percent on top of external quotes for scope change and FX movement.",
            ],
        ),
        (
            "14) Full price reference table (line items)",
            [
                "Item | Typical billing | Indicative USD range (verify with vendor)",
                "Domain registration | Annual | $10-40/year",
                "DNS + CDN + WAF (e.g. Cloudflare) | Monthly | $0-25 free tier; Pro ~$20/mo",
                "App + API hosting (VM / PaaS / K8s small) | Monthly | $40-250/mo",
                "Managed PostgreSQL | Monthly | $25-150/mo",
                "Object storage (reports, uploads) | Monthly | $1-30/mo small",
                "Redis / queue | Monthly | $15-80/mo",
                "Secrets manager | Monthly | $5-40/mo small usage",
                "GitHub / GitLab (team) | Monthly | ~$4-19/user/mo",
                "CI minutes (GitHub Actions etc.) | Monthly | $0-300/mo",
                "Observability (Datadog / New Relic / Grafana) | Monthly | $50-500/mo small",
                "Error tracking (Sentry) | Monthly | $0-100/mo",
                "Uptime checks | Monthly | $0-80/mo",
                "LLM API (usage) | Monthly | $50-5,000/mo depending traffic",
                "NewsAPI | Monthly | $0 limited; paid plans often ~$80-450/mo (verify)",
                "X (Twitter) API | Monthly | from ~$100/mo for entry paid tiers historically—verify current X pricing",
                "LinkedIn / Meta commercial APIs | Annual/contract | $0 self-serve limits; enterprise commonly $5k-50k+/year (quote)",
                "SMS (Twilio-class) | Per message | $0.02-0.10/msg varies by route",
                "WhatsApp Business Cloud | Per conversation | vendor metered—budget separately",
                "SMTP / email (SendGrid/Mailgun) | Monthly | $0-50/mo at low volume",
                "SSL certificates | Annual | $0 (Let's Encrypt) or bundled",
                "Penetration test (optional) | One-time | $3,000-15,000",
                "Legal privacy policy (optional) | One-time | $2,000-25,000",
            ],
        ),
    ]
    write_docx(out, sections)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
