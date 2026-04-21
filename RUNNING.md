# Quick Start



## Start API + Dashboard + Expo (Windows PowerShell)



From project root:



```powershell

.\start-all.ps1

```



This opens **three** terminals:



- FastAPI backend on port `8000`

- Streamlit dashboard (uses `venv\Scripts\python.exe` when present)

### API quick reference (local FastAPI)

After the API is up, open **http://127.0.0.1:8000/docs** for interactive OpenAPI.

Useful routes:

- `GET /v1/catalog/public-apis` — JSON list of external APIs (GDELT, NewsAPI, WHO, LLM providers, etc.).
- `GET /v1/models` — minimal OpenAI-style model list (from `CURSOR_AI_MODEL` / `AI_MODEL`).
- `POST /v1/chat/completions` — **OpenAI-compatible proxy**; same request body as OpenAI; set `CURSOR_API_KEY` + `CURSOR_API_BASE_URL` (or `AI_*` / `OPENAI_*`) in `.env`, or send `Authorization: Bearer …` per request.
- `POST /v1/cursor/chat` — small JSON body `{ "message": "…", "system": "…" }` for quick tests (still uses your env LLM keys; not an official Cursor product API).
- `POST /v1/nlp-alerts` — epidemic alert lines for the dashboard.
- `POST /v1/forecast/seir` — SEIR curve JSON.

Copy **`.env.example`** to **`.env`** and add keys. See comments inside `.env.example`.

### Automated admin emails

The dashboard can send:

- A **daily risk summary** at a configured UTC hour.
- An **emergency outbreak alert** when risk score crosses threshold.

Configure SMTP in `.env`:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_USE_TLS`, `ALERT_FROM_EMAIL`

Then in the **Admin** page:

- Enable alerts.
- Add recipient emails (managed by admin).
- Set daily UTC hour + emergency threshold.

- Expo dev server on port **8082** (Metro default **8081** is often busy)



In the **Expo** terminal, the **QR code** is printed as ASCII art. On your phone, open **Expo Go** and scan it.



### Expo only (manual)



```powershell

cd .\mobile-app

npm run start:expo

```



- Same Wi‑Fi as the PC: `--lan` is used.

- Phone on another network: `npm run start:expo:tunnel`



### API URL on a physical phone



In the app, open **API Settings** and set your PC’s LAN URL, for example `http://192.168.x.x:8000` (not `127.0.0.1`).


