# Epiforecast — Vercel landing page

This is a minimal Next.js 14 (App Router) entry that:

1. Pings the FastAPI backend's `/health` endpoint.
2. Shows a "Open live dashboard" button when `NEXT_PUBLIC_DASHBOARD_URL` is set.
3. Links to the developer brief and OpenAPI docs.

> **Important:** Vercel cannot host the Streamlit dashboard (`frontend/app.py`) or
> the FastAPI backend (`backend/api_server.py`). Both need a long-lived Python
> process. Host them separately and point this page at them via env vars.

## Deploy to Vercel

1. In Vercel, **Import Project** from the GitHub repo.
2. Set **Root Directory** to `web`.
3. Framework Preset auto-detects `Next.js`.
4. Add environment variables under **Project Settings → Environment Variables**:

   | Name | Example | Purpose |
   |------|---------|---------|
   | `API_URL` | `https://epiforecast-api.fly.dev` | Server-side `/health` check |
   | `NEXT_PUBLIC_API_URL` | same as above | Browser-side fetch (later) |
   | `NEXT_PUBLIC_DASHBOARD_URL` | `https://epiforecast.streamlit.app` | "Open live dashboard" button |
   | `NEXT_PUBLIC_SITE_TAGLINE` | `Epidemic intelligence + forecasts` | Header tagline |

5. Click **Deploy**.

## Hosting the Python services

| Service | Code path | Recommended hosts |
|---------|-----------|-------------------|
| Streamlit dashboard | `frontend/app.py` | Streamlit Community Cloud · Hugging Face Spaces · Render · Fly · Railway |
| FastAPI backend | `backend/api_server.py` | Render · Fly · Railway · Google Cloud Run |

The FastAPI backend must set `API_CORS_ORIGINS` to include your Vercel
deployment URL (and `http://localhost:3000` for local dev).

## Local dev

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```
