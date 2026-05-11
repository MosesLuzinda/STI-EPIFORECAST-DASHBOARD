import asyncio
import json
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request as StarletteRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .ai_config import llm_openai_compatible_chain, openai_compatible_env_credentials
from .project_paths import PROJECT_ROOT
from .signal_store import count_recent as _signal_count_recent
from .statistical_forecast import no_ai_mode, nlp_alerts_statistical

load_dotenv(PROJECT_ROOT / ".env")


class AlertRequest(BaseModel):
    disease: str = Field(default="Cholera", min_length=2, max_length=40)
    news_mentions: int = Field(default=1200, ge=0, le=1_000_000_000)
    cholera_cases: int = Field(default=38000, ge=0, le=1_000_000_000)
    affected_countries: int = Field(default=20, ge=0, le=500)


class AlertResponse(BaseModel):
    source: Literal["ai", "fallback", "statistical"]
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
    title="Pathogen Economy Epiforecast API",
    version="1.1.0",
    description=(
        "Epidemic dashboard backend: SEIR forecast, NLP alerts, and an OpenAI-compatible "
        "`/v1/chat/completions` proxy. Configure `CURSOR_*` / `AI_*` env vars to point at any "
        "OpenAI-compatible provider (OpenAI, xAI, Groq, OpenRouter, etc.). "
        "This is not an official Cursor IDE product API."
    ),
)


def _cors_allow_origins() -> list[str]:
    raw = (os.getenv("API_CORS_ORIGINS") or "").strip()
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]


_cors_origins = _cors_allow_origins()
if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


_RATE_LIMIT_PER_MIN = max(0, _env_int("API_RATE_LIMIT_PER_MIN", 120))
_RATE_LIMIT_WINDOW_SEC = 60.0
_UPSTREAM_TIMEOUT_SEC = max(5.0, _env_float("API_UPSTREAM_TIMEOUT_SEC", 90.0))
_MAX_COMPLETION_TOKENS = max(64, _env_int("API_MAX_COMPLETION_TOKENS", 800))
_ALERTS_CACHE_TTL_SEC = max(0, _env_int("ALERTS_CACHE_TTL_SEC", 180))
_rate_limit_lock = threading.Lock()
_rate_limit_hits: dict[str, deque[float]] = defaultdict(deque)
_alerts_cache_lock = threading.Lock()
_alerts_cache: dict[str, tuple[float, Dict[str, object]]] = {}


def _client_id(request: StarletteRequest) -> str:
    xfwd = (request.headers.get("x-forwarded-for") or "").strip()
    if xfwd:
        return xfwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_rate_limited(request: StarletteRequest) -> tuple[bool, int]:
    if _RATE_LIMIT_PER_MIN <= 0:
        return False, _RATE_LIMIT_PER_MIN
    if request.url.path == "/health":
        return False, _RATE_LIMIT_PER_MIN
    now = time.time()
    key = _client_id(request)
    with _rate_limit_lock:
        q = _rate_limit_hits[key]
        while q and (now - q[0]) > _RATE_LIMIT_WINDOW_SEC:
            q.popleft()
        if len(q) >= _RATE_LIMIT_PER_MIN:
            return True, max(0, _RATE_LIMIT_PER_MIN - len(q))
        q.append(now)
        return False, max(0, _RATE_LIMIT_PER_MIN - len(q))


@app.middleware("http")
async def basic_rate_limit_middleware(request: StarletteRequest, call_next):
    limited, remaining = _is_rate_limited(request)
    if limited:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "60", "X-RateLimit-Remaining": "0"},
            content={
                "error": {
                    "type": "rate_limit_error",
                    "message": "Too many requests. Slow down and retry shortly.",
                }
            },
        )
    response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


def _fallback_alerts(disease: str) -> List[str]:
    return [
        f"NLP Alert • {disease} mention velocity is increasing in regional media clusters.",
        "NLP Alert • Public sentiment indicates concern around diagnostics and treatment access.",
        "NLP Alert • Border-adjacent districts dominate high-risk discussion channels.",
        "NLP Alert • Recommendation: activate daily surveillance briefs and rapid response reviews.",
    ]


def _call_ai_for_alerts(payload: AlertRequest) -> Dict[str, object]:
    cache_key = json.dumps(payload.model_dump(), sort_keys=True)
    if _ALERTS_CACHE_TTL_SEC > 0:
        now = time.time()
        with _alerts_cache_lock:
            cached = _alerts_cache.get(cache_key)
            if cached and (now - cached[0]) <= _ALERTS_CACHE_TTL_SEC:
                return dict(cached[1])

    for api_key, base_url, model in llm_openai_compatible_chain():
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
            with urlopen(req, timeout=_UPSTREAM_TIMEOUT_SEC) as response:
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
            result = {"source": "ai", "model": model, "alerts": alerts[:4]}
            if _ALERTS_CACHE_TTL_SEC > 0:
                with _alerts_cache_lock:
                    _alerts_cache[cache_key] = (time.time(), dict(result))
            return result
        except (HTTPError, URLError, TimeoutError, KeyError, ValueError):
            continue

    return {"source": "fallback", "model": "fallback-simulated", "alerts": _fallback_alerts(payload.disease)}


def _upstream_chat_post(url: str, token: str, body: bytes) -> Tuple[int, bytes]:
    req = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=_UPSTREAM_TIMEOUT_SEC) as response:
        return response.status, response.read()


def _public_api_catalog() -> Dict[str, Any]:
    """Curated list of APIs the dashboard can use (keys optional where noted)."""
    return {
        "project": "Pathogen Economy Epiforecast",
        "note": "Cursor the IDE does not publish a public HTTP API for chat. Use OpenAI-compatible providers below.",
        "llm_openai_compatible": [
            {
                "name": "Self-hosted / Ollama (zero API spend)",
                "base_url": "http://localhost:11434/v1",
                "signup": "https://ollama.com/",
                "env": ["LOCAL_LLM_URL", "OLLAMA_BASE_URL", "LOCAL_LLM_MODEL"],
            },
            {
                "name": "LiteLLM proxy (OpenAI-compatible → many providers)",
                "base_url": "http://localhost:4000/v1",
                "signup": "https://docs.litellm.ai/",
            },
            {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "signup": "https://platform.openai.com/"},
            {
                "name": "Google AI Studio (Gemini)",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "signup": "https://aistudio.google.com/",
                "env_aliases": ["GEMINI_API_KEY", "GOOGLE_AI_API_KEY", "AI_API_KEY"],
            },
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
    return {"status": "ok", "service": "pathogen-economy-epiforecast-api"}


@app.get("/v1/catalog/public-apis")
def public_api_catalog():
    """JSON list of useful public / partner APIs and signup links."""
    return _public_api_catalog()


@app.get("/v1/models")
def list_models():
    """Minimal OpenAI-style model list (default model from env)."""
    _, _, model = openai_compatible_env_credentials()
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "pathogen-economy-epiforecast",
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

    env_key, base_url, default_model = openai_compatible_env_credentials()
    chain = llm_openai_compatible_chain()
    auth_header = request.headers.get("authorization") or ""
    token = None
    if auth_header.lower().startswith("bearer ") and len(auth_header.strip()) > 12:
        token = auth_header[7:].strip()

    if not token and not chain:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": (
                        "Missing API key. Set AI_API_KEY / OPENAI_API_KEY (primary) and optionally "
                        "AI_FAILOVER_API_KEY or GROQ_API_KEY, or send Authorization: Bearer."
                    ),
                    "type": "invalid_request_error",
                }
            },
        )

    if not payload.get("model"):
        payload["model"] = default_model

    # Protect against runaway token costs while allowing override via env.
    if isinstance(payload.get("max_tokens"), int):
        payload["max_tokens"] = max(1, min(payload["max_tokens"], _MAX_COMPLETION_TOKENS))
    elif isinstance(payload.get("max_completion_tokens"), int):
        payload["max_completion_tokens"] = max(
            1, min(payload["max_completion_tokens"], _MAX_COMPLETION_TOKENS)
        )

    def _apply_token_cap(pl: Dict[str, Any]) -> None:
        if isinstance(pl.get("max_tokens"), int):
            pl["max_tokens"] = max(1, min(pl["max_tokens"], _MAX_COMPLETION_TOKENS))
        elif isinstance(pl.get("max_completion_tokens"), int):
            pl["max_completion_tokens"] = max(
                1, min(pl["max_completion_tokens"], _MAX_COMPLETION_TOKENS)
            )

    if token:
        key = token
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

    last_err_json: Dict[str, Any] | None = None
    last_status = 502
    for idx, (pkey, pbase, pm) in enumerate(chain):
        pl = dict(payload)
        if idx > 0:
            pl["model"] = pm
        _apply_token_cap(pl)
        endpoint = f"{pbase}/chat/completions"
        outgoing = json.dumps(pl).encode("utf-8")
        try:
            status, raw = await asyncio.to_thread(_upstream_chat_post, endpoint, pkey, outgoing)
        except HTTPError as exc:
            err_text = exc.read().decode("utf-8", errors="replace")
            try:
                last_err_json = json.loads(err_text)
            except json.JSONDecodeError:
                last_err_json = {"error": {"message": err_text[:800], "type": "upstream_error"}}
            last_status = int(exc.code or 502)
            continue
        except (URLError, TimeoutError, OSError) as exc:
            last_err_json = {"error": {"message": str(exc)[:500], "type": "upstream_unreachable"}}
            last_status = 502
            continue
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            last_err_json = {"error": {"message": "Upstream returned non-JSON", "type": "upstream_error"}}
            last_status = 502
            continue
        return JSONResponse(content=parsed, status_code=status)

    return JSONResponse(
        content=last_err_json
        or {"error": {"message": "All configured LLM providers failed.", "type": "upstream_error"}},
        status_code=last_status,
    )


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
    chain = llm_openai_compatible_chain()
    if not chain:
        raise HTTPException(
            status_code=503,
            detail="No LLM API key configured (primary AI_* / OPENAI_* and optional AI_FAILOVER_* / GROQ_*).",
        )
    last_detail = "All configured LLM providers failed."
    for idx, (api_key, base_url, pm) in enumerate(chain):
        if idx == 0:
            model = body.model or pm
        else:
            model = pm
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
            last_detail = err_text[:2000]
            continue
        except (URLError, TimeoutError, OSError) as exc:
            last_detail = str(exc)
            continue
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            last_detail = "Upstream returned non-JSON"
            continue
        return JSONResponse(content=parsed, status_code=status)

    raise HTTPException(status_code=502, detail=last_detail[:2000])


@app.post("/v1/nlp-alerts", response_model=AlertResponse)
def nlp_alerts(request: AlertRequest):
    if no_ai_mode():
        try:
            vs24 = int(_signal_count_recent(24))
        except Exception:
            vs24 = 0
        lines, _ = nlp_alerts_statistical(
            request.disease,
            request.news_mentions,
            request.cholera_cases,
            request.affected_countries,
            validated_signals_24h=vs24,
        )
        return AlertResponse(source="statistical", model="rules-thresholds", alerts=lines)
    result = _call_ai_for_alerts(request)
    return AlertResponse(**result)


@app.post("/v1/forecast/seir", response_model=ForecastResponse)
def forecast_seir(request: ForecastRequest):
    try:
        return _seir_forecast(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Forecast generation failed: {exc}") from exc

