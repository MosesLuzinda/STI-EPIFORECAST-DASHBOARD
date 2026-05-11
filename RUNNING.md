# Quick Start



## Web UI on Vercel (Next.js)

The **Streamlit** app under `frontend/` is not compatible with Vercel. The new shell lives in **`web/`** (Next.js 14).

1. Deploy the repo to Vercel and set the project **Root Directory** to **`web`** (or connect the repo and choose `web` as the root when importing).
2. In Vercel → *Settings → Environment Variables*, set **`API_URL`** to your **public FastAPI base URL** (no trailing slash), for example `https://epiforecast-api.onrender.com`.
3. On the FastAPI host, set **`API_CORS_ORIGINS`** to your Vercel origin(s), comma-separated, e.g. `https://your-app.vercel.app,http://localhost:3000`.

Run Next locally from `web/`:

```powershell
cd .\web
copy .env.example .env
# edit .env — API_URL should match where uvicorn is listening
npm install
npm run dev
```

Open http://localhost:3000 — the home page calls **`GET /health`** on the FastAPI server.

**Important:** Keep **`uvicorn backend.api_server:app`** (or your process wrapper) running on a **long-lived** host (Render, Fly.io, Railway, a VM, etc.). Vercel only serves the Next.js frontend in this layout.



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


