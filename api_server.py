import asyncio
import os
import json
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Request as StarletteRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class AlertRequest(BaseModel):
    disease: str = Field(default="Cholera", min_length=2, max_length=40)
    news_mentions: int = Field(default=1200, ge=0, le=1_000_000_000)
    cholera_cases: int = Field(default=38000, ge=0, le=1_000_000_000)
    affected_countries: int = Field(default=20, ge=0, le=500)


class AlertResponse(BaseModel):
    source: Literal["ai", "fallback"]
    model: str
    alerts: List[str]


class ForecastRequest(BaseModel):
    disease: str = Field(default="Cholera")
    population: int = Field(default=48_000_000, ge=1000)
    initial_infected: int = Field(default=12_000, ge=1)
    days: int = Field(default=100, ge=7, le=180)
    intervention_effectiveness: float = Field(default=0.35, ge=0.0, le=0.95)


class ForecastPoint(BaseModel):
    day: int
    susceptible: int
    exposed: int
    infected: int
    recovered: int


class ForecastResponse(BaseModel):
    disease: str
    horizon_days: int
    points: List[ForecastPoint]


app = FastAPI(
    title="STI-EPI-FORECAST API",
    version="1.1.0",
    description=(
        "Epidemic dashboard backend: SEIR forecast, NLP alerts, and an OpenAI-compatible "
        "`/v1/chat/completions` proxy. Configure `CURSOR_*` / `AI_*` env vars to point at any "
        "OpenAI-compatible provider (OpenAI, xAI, Groq, OpenRouter, etc.). "
        "This is not an official Cursor IDE product API."
    ),
)


def _fallback_alerts(disease: str) -> List[str]:
    return [
        f"NLP Alert • {disease} mention velocity is increasing in regional media clusters.",
        "NLP Alert • Public sentiment indicates concern around diagnostics and treatment access.",
        "NLP Alert • Border-adjacent districts dominate high-risk discussion channels.",
        "NLP Alert • Recommendation: activate daily surveillance briefs and rapid response reviews.",
    ]


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


def _call_ai_for_alerts(payload: AlertRequest) -> Dict[str, object]:
    api_key, base_url, model = _ai_env_credentials()
    if not api_key:
        return {"source": "fallback", "model": "fallback-simulated", "alerts": _fallback_alerts(payload.disease)}
    endpoint = f"{base_url}/chat/completions"
    system_prompt = (
        "You are an epidemiology surveillance assistant. "
        "Return exactly 4 concise alert lines. "
        "Each line must start with 'NLP Alert •'."
    )
    user_prompt = (
        f"Disease: {payload.disease}\n"
        f"News mentions (24h): {payload.news_mentions}\n"
        f"Estimated cholera cases: {payload.cholera_cases}\n"
        f"Affected countries: {payload.affected_countries}\n"
        "Output only the 4 alert lines."
    )

    try:
        request_body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.25,
        }
        req = Request(
            endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(req, timeout=25) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
        content = parsed["choices"][0]["message"]["content"]
        lines = [line.strip("- ").strip() for line in content.splitlines() if line.strip()]

        alerts: List[str] = []
        for line in lines:
            normalized = line if line.startswith("NLP Alert") else f"NLP Alert • {line}"
            alerts.append(normalized)
        if len(alerts) < 4:
            alerts.extend(_fallback_alerts(payload.disease)[: 4 - len(alerts)])
        return {"source": "ai", "model": model, "alerts": alerts[:4]}
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError):
        return {"source": "fallback", "model": "fallback-simulated", "alerts": _fallback_alerts(payload.disease)}


def _upstream_chat_post(url: str, token: str, body: bytes) -> Tuple[int, bytes]:
    req = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=120) as response:
        return response.status, response.read()


def _public_api_catalog() -> Dict[str, Any]:
    """Curated list of APIs the dashboard can use (keys optional where noted)."""
    return {
        "project": "STI-EPI-FORECAST",
        "note": "Cursor the IDE does not publish a public HTTP API for chat. Use OpenAI-compatible providers below.",
        "llm_openai_compatible": [
            {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "signup": "https://platform.openai.com/"},
            {"name": "xAI", "base_url": "https://api.x.ai/v1", "signup": "https://console.x.ai/"},
            {"name": "Groq", "base_url": "https://api.groq.com/openai/v1", "signup": "https://console.groq.com/"},
            {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "signup": "https://openrouter.ai/"},
        ],
        "news_and_social_open_web": [
            {"name": "GDELT DOC API", "key_required": False, "docs": "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"},
            {"name": "NewsAPI", "key_required": True, "env": "NEWSAPI_KEY", "signup": "https://newsapi.org/"},
            {"name": "Reddit JSON (public)", "key_required": False, "docs": "https://github.com/reddit-archive/reddit/wiki/API"},
            {"name": "Hacker News Algolia", "key_required": False, "docs": "https://hn.algolia.com/api"},
        ],
        "health_data": [
            {"name": "Our World in Data (CSV)", "key_required": False, "example": "https://ourworldindata.org/grapher/death-rate-from-malaria.csv"},
            {"name": "WHO GHO OData", "key_required": False, "docs": "https://www.who.int/data/gho/info/gho-odata-api"},
        ],
        "this_server_endpoints": [
            "GET /health",
            "GET /v1/catalog/public-apis",
            "GET /v1/models",
            "POST /v1/nlp-alerts",
            "POST /v1/chat/completions",
            "POST /v1/cursor/chat",
            "POST /v1/forecast/seir",
        ],
    }


def _seir_forecast(req: ForecastRequest) -> ForecastResponse:
    disease_beta = {"cholera": 0.36, "malaria": 0.31, "typhoid": 0.27, "marburg": 0.44}
    beta = disease_beta.get(req.disease.lower(), 0.33) * (1.0 - req.intervention_effectiveness)
    sigma = 1 / 5.2
    gamma = 1 / 8.5

    s = float(req.population - req.initial_infected)
    e = float(req.initial_infected * 0.45)
    i = float(req.initial_infected)
    r = 0.0
    points = [ForecastPoint(day=0, susceptible=int(s), exposed=int(e), infected=int(i), recovered=int(r))]

    for day in range(1, req.days + 1):
        new_exposed = beta * s * i / req.population
        new_infectious = sigma * e
        recovered = gamma * i
        s = max(0.0, s - new_exposed)
        e = max(0.0, e + new_exposed - new_infectious)
        i = max(0.0, i + new_infectious - recovered)
        r = max(0.0, r + recovered)
        points.append(ForecastPoint(day=day, susceptible=int(s), exposed=int(e), infected=int(i), recovered=int(r)))

    return ForecastResponse(disease=req.disease, horizon_days=req.days, points=points)


@app.get("/health")
def health():
    return {"status": "ok", "service": "sti-epi-forecast-api"}


@app.get("/v1/catalog/public-apis")
def public_api_catalog():
    """JSON list of useful public / partner APIs and signup links."""
    return _public_api_catalog()


@app.get("/v1/models")
def list_models():
    """Minimal OpenAI-style model list (default model from env)."""
    _, _, model = _ai_env_credentials()
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "sti-epi-forecast",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions_proxy(request: StarletteRequest):
    """
    OpenAI-compatible proxy: forwards JSON body to `{AI_BASE_URL}/chat/completions`.
    Use env key, or send `Authorization: Bearer <token>` to override per request.
    """
    body_bytes = await request.body()
    try:
        payload: Dict[str, Any] = json.loads(body_bytes or b"{}")
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
        )

    env_key, base_url, default_model = _ai_env_credentials()
    auth_header = request.headers.get("authorization") or ""
    token = None
    if auth_header.lower().startswith("bearer ") and len(auth_header.strip()) > 12:
        token = auth_header[7:].strip()
    key = token or env_key
    if not key:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Missing API key. Set CURSOR_API_KEY or AI_API_KEY, or send Authorization: Bearer.",
                    "type": "invalid_request_error",
                }
            },
        )

    if not payload.get("model"):
        payload["model"] = default_model

    endpoint = f"{base_url}/chat/completions"
    outgoing = json.dumps(payload).encode("utf-8")

    try:
        status, raw = await asyncio.to_thread(_upstream_chat_post, endpoint, key, outgoing)
    except HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_text)
        except json.JSONDecodeError:
            err_json = {"error": {"message": err_text[:800], "type": "upstream_error"}}
        return JSONResponse(content=err_json, status_code=exc.code)
    except (URLError, TimeoutError, OSError) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc)[:500], "type": "upstream_unreachable"}},
        )

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": "Upstream returned non-JSON", "type": "upstream_error"}},
        )
    return JSONResponse(content=parsed, status_code=status)


class CursorChatRequest(BaseModel):
    """Small helper body for quick tests (maps to chat/completions)."""

    message: str = Field(default="Summarize cholera surveillance priorities in 3 bullets.", min_length=1, max_length=8000)
    model: Optional[str] = Field(default=None, max_length=128)
    system: str = Field(
        default="You are a concise epidemiology assistant for government dashboards.",
        max_length=4000,
    )


@app.post("/v1/cursor/chat")
def cursor_style_chat(body: CursorChatRequest):
    """
    Convenience endpoint (not affiliated with Cursor IDE): single user message → chat completion.
    Same credentials as `/v1/chat/completions`.
    """
    api_key, base_url, default_model = _ai_env_credentials()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="No LLM API key configured (CURSOR_API_KEY, AI_API_KEY, OPENAI_API_KEY, or XAI_API_KEY).",
        )
    model = body.model or default_model
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": body.system},
            {"role": "user", "content": body.message},
        ],
        "temperature": 0.35,
    }
    endpoint = f"{base_url}/chat/completions"
    try:
        status, raw = _upstream_chat_post(endpoint, api_key, json.dumps(request_body).encode("utf-8"))
    except HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=exc.code, detail=err_text[:2000]) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Upstream returned non-JSON") from exc
    return JSONResponse(content=parsed, status_code=status)


@app.post("/v1/nlp-alerts", response_model=AlertResponse)
def nlp_alerts(request: AlertRequest):
    result = _call_ai_for_alerts(request)
    return AlertResponse(**result)


@app.post("/v1/forecast/seir", response_model=ForecastResponse)
def forecast_seir(request: ForecastRequest):
    try:
        return _seir_forecast(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Forecast generation failed: {exc}") from exc

