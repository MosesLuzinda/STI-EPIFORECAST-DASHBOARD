# Pathogen Economy Epiforecast — Developer Brief

A vendor-neutral specification. The developer is free to choose any framework,
database, hosting platform, charting library, or AI provider. This document
describes **what** the system must do, not **how** to implement it.

---

## 1. Purpose

A web-based **epidemic intelligence and forecast platform** that:

- Continuously ingests open-source health signals from the public web and official agencies.
- Filters, validates, and stores them as a structured **signal database**.
- Surfaces them as **live dashboards, forecasts, briefings, and decision aids** for
  public-health operators, policy makers, and pathogen-economy investors.
- Exposes an **AI assistant ("Coolio")** that interprets the data, answers
  natural-language commands, and writes briefings — while remaining safe
  (allow-listed actions only, no arbitrary code execution).

The system must work in three operating modes:

1. **Full mode** — live feeds + AI enabled.
2. **No-AI mode** — every AI-dependent output degrades to a deterministic rule-based equivalent.
3. **Offline mode** — no external HTTP calls at all; the system runs on locally
   stored signals and previously cached data.

---

## 2. Users / Personas

| Persona | Primary need |
|---|---|
| National epidemic operator | Today's situation, hotspots, response checklist |
| Policy maker / executive | One-page strategic brief, KPI deltas, action lists |
| Researcher / forecaster | Per-disease forecasts, history, drivers, uncertainty |
| Pathogen-economy investor / planner | ROI matrices, surge plans, regional market data, venture decisions |
| Administrator | Feed health, alert thresholds, recipients, exports |
| Field user | Ask the assistant in plain language; jump between views fast |

---

## 3. High-level architecture (conceptual)

Three logical layers — the developer picks the technology for each:

1. **Backend services**
   - Feed ingestion (parallel fetch, per-source timeouts, fallback to cache).
   - Signal validation pipeline (cheap keyword pre-filter → AI classification →
     persisted "approved" record).
   - Forecast engine (statistical ensemble + optional AI narration).
   - AI orchestration layer (provider-agnostic; supports cloud, self-hosted, or
     local models interchangeably).
   - Local persistence (signal store, configuration, alert recipients, memory of
     past briefings).

2. **API layer**
   - Internal API consumed by the UI for any data not directly served from the
     backend.
   - At least one endpoint for **NLP alerts** and one **chat-style proxy** that
     re-uses the AI orchestration layer.
   - Rate limiting and CORS protection.

3. **Frontend (web UI)**
   - Sidebar (controls), top navigation (groups), main page area.
   - Pages: Home, National dashboard, Disease Surveillance, Disease Profiler,
     Forecast Lab, Hotspots map, Global Surveillance, Executive Briefing,
     Action Plan, Reports library, Admin, Developers, Pathogen Workspace,
     VDTEC & ROI, Clinical trial sites, Medical-supplies surge, Regional market,
     7-1-7 impact estimator, Venture matrix, ROI & Financing, Think Tank.
   - **Coolio command panel** in the sidebar (free-text input → safe intent routing).
   - **Optional chat panel** for free-form questions to the AI.

---

## 4. Functional features

### 4.1 Signal ingestion
- Pull from **public news indexes, public social search APIs, public discussion
  sites, official agency RSS feeds, official health authority publications,
  regional public-health bulletins, humanitarian/disaster feeds, and optional
  press-release APIs**.
- Each source runs in **parallel** with its own short timeout; the whole snapshot
  has a single **cold-start network deadline** (configurable). Sources that miss
  the deadline degrade gracefully without breaking the page.
- Snapshots are **cached** for a short TTL (default 5 minutes) and refreshed on demand.

### 4.2 Signal validation
- Cheap **keyword pre-filter** (outbreak vocabulary: pathogen names +
  epidemiology terms) drops obvious non-events.
- Surviving items go through an **AI classifier** in small batches. The model
  returns a structured decision: *is this an outbreak signal? confidence,
  disease, location, reason*.
- Only items with high enough confidence are persisted.
- A daily quota / rate cap on AI calls protects budget.
- When AI is disabled, validation falls back to the keyword filter alone.

### 4.3 Signal store
- Local persistent store (developer's choice of storage engine).
- Captures: timestamp (UTC), disease, location, source, source tier
  (official / open-web / social), title, URL, confidence, raw text snippet.
- Supports queries: total in last N hours, per-disease counts, per-source-tier
  counts, daily aggregates, list of distinct diseases.
- Records are append-only; older records are kept for historical comparison.

### 4.4 Dashboards

**Home** — hero panel with:
- AI assistant branding and tagline.
- Live **signal index** (0–100) + risk level.
- KPIs: news & social volume, agency volume, sources online.
- **3D "signal skyline"** chart: one tower per pathogen, height = real validated
  24h count.
- Quick-jump buttons to every major view.

**National dashboard** — full KPI grid, agency vs. open-web tabs, news mentions,
recent alerts, source detail lists, drilldowns.

**Disease Surveillance** — pick a disease (or none), show daily trend, last
validated events, AI-driven NLP alerts, ML-based short-horizon trend,
expert/lay narrative.

**Disease Profiler** — encyclopedic profile of any disease.

**Forecast Lab** — for a chosen disease:
- Statistical ensemble forecast over a chosen horizon, with confidence bands.
- Backtest metrics.
- Top driving features.
- Optional AI **briefing** that interprets the numbers (never overrides them).
- When local history is too thin, automatically switch to a **world-context
  briefing** (retrieval-based summary + AI synthesis).

**Hotspots / Global Surveillance** — maps with risk-tinted regions / countries;
click for drilldown.

**Executive Briefing** — one-page summary with KPIs, current actions,
who needs to know.

**Action Plan / Response checklist** — generated from the active state.

**Reports library** — downloadable / pre-rendered reports (DOCX/PDF or similar).

**Pathogen Workspace / VDTEC ROI / Venture matrix / 7-1-7 / Medical-supplies
surge / Regional market / ROI & Financing / Think Tank** — planning and
economic-decision modules.

**Admin** — alert recipients, thresholds, feed health, AI key status, manual
feed test, periodic-email controls.

**Developers** — API reference, env vars, integration notes.

### 4.5 AI assistant ("Coolio")

The system has an AI layer with these surfaces, all sharing one provider router:

1. **Forecast narration** — when a forecast finishes, AI writes a structured
   interpretation (trajectory read, uncertainty, pattern spotter, watch-list).
   It must **never replace the numeric outputs**.
2. **World briefing** — when local history is empty or too short, build a
   retrieval pack from public encyclopedic sources + official RSS + open data
   sets, then ask AI to synthesize a snapshot with a clear *Limitations* line.
3. **NLP alerts** — four short alert lines per active disease, generated from
   current KPIs.
4. **Signal classification** — described above.
5. **Command router** — sidebar text box. User types in natural language; AI
   maps it to **one** allow-listed action: *navigate to page X / set watched
   disease Y / refresh data / show help / unclear*. No free-form code execution.
   Free-text phrasing — no hardcoded phrase list.
6. **Optional chat panel** — free-form Q&A on the active dashboard context.

#### AI orchestration requirements
- One central provider router; the rest of the system talks to it.
- Supports **local self-hosted models** (when a local model URL is configured,
  it takes priority over cloud providers).
- Supports multiple cloud providers interchangeably; the router resolves base
  URL and model from environment.
- Supports an automatic **failover provider** when the primary errors.
- **Token budget**: a single helper reads "max tokens" per surface from env.
  Values `0`, `unlimited`, `omit` → no app-side cap (provider decides).
  Positive integers → hard cap. Anything else → safe default.
- **Global kill switch**: one env flag disables every AI call; the entire UI
  must still work in this mode.
- **Single "is AI configured?" predicate** used by the UI banners and the
  assistant code paths.

### 4.6 Coolio memory
- Each world briefing can append a short observation (disease, snapshot
  timestamp, key claims, source list) to a **memory store**.
- Subsequent briefings include recent memory as context for continuity.
- Capped by total bytes; oldest entries pruned.

### 4.7 Alerts
- Threshold-based: when a metric crosses a configured threshold, generate an
  **emergency** alert email to the admin list.
- Daily digest at a configured time.
- Multiple delivery transports supported (transactional API or plain SMTP).
- Each alert includes the snapshot UTC timestamp and a link back to the dashboard.

### 4.8 Refresh and timeliness
- Cold-start network deadline is **env-tunable** (3–20 s; default ~7 s).
- Cached snapshot TTL is **env-tunable** (default 5 minutes).
- A periodic auto-refresh interval is optional (env-tunable; off by default).
- Every page shows last-update timestamp (local + UTC).

### 4.9 No auto-selected disease
- When the app starts, **no disease is pre-selected**. The dashboard, KPIs, and
  signal skyline show **every** disease the validator has approved.
- A "no focus — pick a disease" sentinel is the first option in both the sidebar
  and top-bar selectors.
- Module pages that need a specific disease prompt the user to choose if none
  is set.

### 4.10 Visual design
- Cinematic 3D ambient backdrop (animated, GPU-friendly) behind every page.
- Subtle 3D tilt on cards/metrics on hover.
- Respects user OS **reduced-motion** preference (animations slow rather than
  disable).
- Consistent typography, rounded surfaces, soft shadows, color-coded risk chips.
- The AI assistant has a visual identity (animated orb, nameplate, gradient title).
- One 3D data chart on the home page that is **driven by real data** (validated
  24h signal counts), not decorative noise.

### 4.11 Internationalization & accessibility
- All copy is in plain English; structure leaves room for future localization.
- Color is never the only signal; risk levels include text + chip.
- Animations honor `prefers-reduced-motion`.
- Keyboard-reachable controls; semantic headings.

---

## 5. Non-functional requirements

| Concern | Requirement |
|---|---|
| **Privacy** | No personal health information collected. No outbound calls in offline mode. |
| **Security** | Allow-listed action router for the assistant. Optional API rate-limit. CORS configurable. |
| **Resilience** | Any individual feed can fail without breaking the dashboard. Cached snapshot is reused on transient failures. |
| **Configurability** | Everything tunable via environment variables (rate limits, timeouts, AI on/off, feed deadline, cache TTL, memory cap, alert thresholds, recipients). Sample config file documents every variable. |
| **Portability** | Runs on a developer laptop with no paid API by default. Cloud deployment is documented but optional. |
| **Observability** | Per-feed last-latency, last-error, retry count surfaced in Admin. Snapshot UTC timestamp on every page. |
| **Cost control** | AI calls are bounded per snapshot; daily caps for the signal validator; cache aggressively. |
| **Audit** | Each persisted signal records the source URL and the reason it was kept. |

---

## 6. Data sources (categories, not vendors)

- Public news / event indexes (article volume + top articles).
- Public discussion APIs (post counts + items).
- Aggregator news search (story counts + items).
- Optional commercial news API.
- Official agency RSS feeds (world health authority, regional offices, national
  agency, intergovernmental, humanitarian disaster, infectious-disease research
  center, regional public-health organization).
- Open data CSVs / portals (e.g., open historical pandemic series).
- Optional enterprise social APIs (when tokens are configured).

The developer must implement a **uniform fetch wrapper** with per-source timeout,
retry policy, and graceful degradation.

---

## 7. Inputs / Outputs

**Inputs**
- Environment configuration file (single source of truth for all env vars, with comments).
- Optional preset watch list of diseases.
- Optional pre-seeded local signal database.

**Outputs**
- Live web UI.
- Internal HTTP API (chat proxy, NLP alerts).
- Email alerts.
- Downloadable reports.
- Memory store of past briefings.
- Signal database snapshot (for backup / external analytics).

---

## 8. Acceptance criteria

The delivery is accepted when the developer can demonstrate:

1. App starts and renders the home dashboard with **no API keys configured at all**,
   using only public feeds and the deterministic fallbacks.
2. Adding any one AI provider's credentials to the env unlocks the assistant
   features automatically — no code changes required.
3. Enabling the global kill switch keeps every page functional with rule-based
   equivalents.
4. The sidebar Coolio command box, with credentials present, correctly maps
   free-form natural language to **only** the allow-listed actions; any unsafe
   phrasing returns an "unclear" response.
5. The home 3D skyline shows real tower heights from the local signal store and
   updates after **Refresh data**.
6. Removing the laptop's internet connection and setting offline mode keeps the
   app usable on locally stored data.
7. Slow feeds beyond the cold-start deadline degrade silently (KPI shows
   "degraded" badge) but the page still loads under ~8 s.
8. The admin email alert is delivered when a threshold is crossed.
9. Reduce-motion preference produces a calmer (not blank) experience.
10. No disease is auto-selected on first load; the focus selector starts on
    the "pick a disease" sentinel.

---

## 9. Out of scope (initial release)

- Individualized medical advice.
- Patient-level records.
- Real-time geolocation tracking of users.
- Direct integration with hospital EMR systems.
- Native mobile apps (web responsive is sufficient).

---

## 10. Stretch goals

- Multi-tenant accounts with role-based access.
- Webhook subscriptions for alerts.
- Export to GIS-compatible formats.
- Free-form chat with full retrieval over the local signal store.
- Localized UI strings (i18n).

---

## 11. Deliverables expected from the developer

- Working source code in a version-controlled repository.
- A `.env.example` documenting every configuration variable with a comment.
- A README covering: install, run, configure, deploy, troubleshoot.
- A short developer reference (or in-app **Developers** page) listing API
  endpoints and how to call them.
- A demo deployment (local or hosted) walking through every acceptance criterion.
- Brief operator handbook for the admin role.

---

*End of brief.*
