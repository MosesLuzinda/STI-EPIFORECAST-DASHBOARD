"""
OpenAI-compatible API routing. xAI (Grok) keys are rejected by api.openai.com;
if the key looks like an xAI key and the base URL still points at OpenAI, we
route to https://api.x.ai/v1 automatically.

For Groq, set e.g. AI_MODEL=grok-2-latest (or your console’s model name).

Failover: set AI_FAILOVER_API_KEY or GROQ_API_KEY (optional base/model) so
chat, signal validation, NLP alerts, and the FastAPI proxy retry on errors.
"""
from __future__ import annotations

from urllib.parse import urlparse

import os
import requests

_DEFAULT_OPENAI = "https://api.openai.com/v1"
_XAI = "https://api.x.ai/v1"
_GEMINI = "https://generativelanguage.googleapis.com/v1beta"


def _looks_like_openai_host(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return True
    if u == _DEFAULT_OPENAI:
        return True
    if "openai.com" in u.lower() and "api.x.ai" not in u.lower():
        return True
    try:
        p = u if u.startswith("http") else f"https://{u}"
        host = urlparse(p).netloc.lower()
        return "api.openai.com" in host or host in ("openai.com", "www.openai.com")
    except Exception:
        return "openai.com" in u.lower()


def resolve_openai_compatible_base_url(api_key: str | None, explicit_base: str | None) -> str:
    k = (api_key or "").strip()
    b = (explicit_base or "").strip().rstrip("/")
    if not b:
        b = _DEFAULT_OPENAI
    if not k.startswith("xai-"):
        return b
    # xAI / Grok keys return 401 from OpenAI; force xAI host unless user already
    # pointed at another provider (e.g. proxy, or explicit https://api.x.ai/v1).
    if "api.x.ai" in b.lower() or b.lower().rstrip("/") == "https://api.x.ai/v1".rstrip("/"):
        return b
    if _looks_like_openai_host(b):
        return _XAI
    return b


def default_chat_model_for_base_url(base_url: str) -> str:
    """
    When AI_MODEL is unset, pick a model that exists on the target host.
    xAI does not host gpt-4o-mini; use a Grok id from your xAI console if needed.
    """
    b = (base_url or "").lower()
    if "generativelanguage.googleapis.com" in b:
        return "gemini-2.0-flash"
    if "api.x.ai" in b or b.rstrip("/").endswith("x.ai/v1"):
        return "grok-2-latest"
    if "groq.com" in b:
        return "llama-3.1-8b-instant"
    return "gpt-4o-mini"


def llm_openai_compatible_chain() -> list[tuple[str, str, str]]:
    """
    Providers that accept POST {base}/chat/completions (OpenAI-compatible).
    Primary env credentials first; then optional failover (Groq, etc.).
    Gemini-native hosts are omitted here — use `chat_text_from_messages` which
    handles Gemini separately.
    """
    chain: list[tuple[str, str, str]] = []
    pk, pb, pm = openai_compatible_env_credentials()
    pb = (pb or "").strip().rstrip("/")
    if pk and not _is_gemini_native(pk, pb):
        chain.append((pk.strip(), pb, pm))

    fk = (os.getenv("AI_FAILOVER_API_KEY") or os.getenv("GROQ_API_KEY") or "").strip()
    if not fk:
        return chain

    fb = (
        os.getenv("AI_FAILOVER_BASE_URL")
        or os.getenv("GROQ_BASE_URL")
        or "https://api.groq.com/openai/v1"
    ).strip().rstrip("/")
    fm = (os.getenv("AI_FAILOVER_MODEL") or os.getenv("GROQ_MODEL") or "").strip()
    if not fm:
        fm = default_chat_model_for_base_url(fb)

    # Avoid duplicate provider if user pointed failover at the same key as primary.
    if chain and fk == chain[0][0] and fb.rstrip("/") == chain[0][1].rstrip("/"):
        return chain
    chain.append((fk, fb, fm))
    return chain


def openai_compatible_env_credentials() -> tuple[str | None, str, str]:
    """
    One place for (api_key, base_url, model) used by Streamlit, FastAPI, the signal
    validator, and Forecast Lab. Resolves xAI keys to https://api.x.ai/v1 when needed.
    """
    api_key = (
        os.getenv("CURSOR_API_KEY")
        or os.getenv("AI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("XAI_API_KEY")
    )
    explicit = (
        os.getenv("CURSOR_API_BASE_URL")
        or os.getenv("AI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or ""
    ).strip()
    base = resolve_openai_compatible_base_url(api_key, explicit).rstrip("/")
    env_model = (os.getenv("CURSOR_AI_MODEL") or os.getenv("AI_MODEL") or "").strip()
    model = env_model or default_chat_model_for_base_url(base)
    return api_key, base, model


def _is_gemini_native(api_key: str | None, base_url: str) -> bool:
    key = (api_key or "").strip()
    base = (base_url or "").strip().lower()
    return key.startswith("AIza") or "generativelanguage.googleapis.com" in base


def _gemini_native_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return _GEMINI
    if base.endswith("/openai"):
        return base[: -len("/openai")]
    return base


def chat_text_from_messages(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    timeout_sec: float = 35.0,
    max_tokens: int | None = None,
    model: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Provider-agnostic chat helper.
    Returns (assistant_text, error_message) and supports:
    - OpenAI-compatible providers (/chat/completions)
    - Native Gemini (models/*:generateContent)
    """
    api_key, base_url, default_model = openai_compatible_env_credentials()
    if api_key and _is_gemini_native(api_key, base_url):
        use_model = (model or default_model or "gpt-4o-mini").strip()
        native_base = _gemini_native_base(base_url)
        system_text = ""
        user_parts: list[str] = []
        for msg in messages:
            role = str(msg.get("role") or "").strip().lower()
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                system_text = f"{system_text}\n{content}".strip() if system_text else content
            else:
                user_parts.append(f"{role}: {content}" if role and role != "user" else content)

        payload: dict = {
            "contents": [{"role": "user", "parts": [{"text": "\n\n".join(user_parts).strip()}]}],
            "generationConfig": {"temperature": float(temperature)},
        }
        if max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = int(max_tokens)
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        try:
            resp = requests.post(
                f"{native_base}/models/{use_model}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=timeout_sec,
            )
            if resp.status_code != 200:
                return None, f"Gemini HTTP {resp.status_code}: {resp.text[:400]}"
            body = resp.json()
            candidates = body.get("candidates") or []
            if not candidates:
                return None, "Gemini returned no candidates"
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "\n".join(str(p.get("text") or "").strip() for p in parts if str(p.get("text") or "").strip()).strip()
            if not text:
                return None, "Gemini response had no text content"
            return text, None
        except Exception as exc:
            return None, str(exc)

    chain = llm_openai_compatible_chain()
    if not chain:
        return None, "No AI API key configured"

    payload_template = {
        "messages": messages,
        "temperature": float(temperature),
    }
    if max_tokens is not None:
        payload_template["max_tokens"] = int(max_tokens)

    last_err: str | None = None
    for key, base, mdl in chain:
        use_model = (model or mdl or "gpt-4o-mini").strip()
        body = dict(payload_template)
        body["model"] = use_model
        try:
            resp = requests.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
                timeout=timeout_sec,
            )
            if resp.status_code != 200:
                last_err = f"Upstream HTTP {resp.status_code}: {resp.text[:400]}"
                continue
            data = resp.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            if not content:
                last_err = "Upstream response missing assistant content"
                continue
            return str(content).strip(), None
        except Exception as exc:
            last_err = str(exc)
            continue

    return None, last_err or "No OpenAI-compatible LLM provider succeeded"


def chat_text_from_prompts(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    timeout_sec: float = 35.0,
    max_tokens: int | None = None,
    model: str | None = None,
) -> tuple[str | None, str | None]:
    return chat_text_from_messages(
        [
            {"role": "system", "content": str(system_prompt or "")},
            {"role": "user", "content": str(user_prompt or "")},
        ],
        temperature=temperature,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        model=model,
    )
