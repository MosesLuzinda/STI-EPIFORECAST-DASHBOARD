"""Check .env API key is set and accepted (no secrets printed)."""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import requests
from dotenv import load_dotenv

from backend.ai_config import openai_compatible_env_credentials

load_dotenv(_ROOT / ".env")


def mask(s: str) -> str:
    if not s:
        return "(not set)"
    s = s.strip()
    if len(s) <= 8:
        return s[:2] + "..." + s[-2:]
    return s[:4] + "..." + s[-4:]


def main() -> None:
    keys = [
        ("CURSOR_API_KEY", os.getenv("CURSOR_API_KEY")),
        ("AI_API_KEY", os.getenv("AI_API_KEY")),
        ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
        ("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")),
        ("GOOGLE_AI_API_KEY", os.getenv("GOOGLE_AI_API_KEY")),
        ("XAI_API_KEY", os.getenv("XAI_API_KEY")),
    ]
    api_key_resolved, base, model = openai_compatible_env_credentials()
    base = (base or "").rstrip("/")

    print("--- Environment (masked) ---")
    local_u = (os.getenv("LOCAL_LLM_URL") or os.getenv("OLLAMA_BASE_URL") or "").strip()
    if local_u:
        print("LOCAL_LLM / Ollama (env):", local_u[:96] + ("..." if len(local_u) > 96 else ""))
    for name, val in keys:
        if val and val.strip():
            print(f"{name}: SET  value: {mask(val)}")
        else:
            print(f"{name}: NOT SET")

    print("Base URL (as app resolves):", base)
    print("Model (as app resolves; default depends on host if AI_MODEL unset):", model)

    used = None
    for name, val in keys:
        if val and val.strip() and val.strip() == (api_key_resolved or ""):
            used = name
            break
    if not used and api_key_resolved:
        used = "resolved (matches app key selection order)"

    if not api_key_resolved:
        print()
        print("RESULT: No API key found. Set LOCAL_LLM_URL for Ollama, or add OPENAI_API_KEY (or similar) to .env")
        raise SystemExit(1)

    url = f"{base}/models"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {api_key_resolved}"},
        timeout=15,
    )
    print()
    print("--- API check GET /models ---")
    print("Using key from:", used)
    print("HTTP status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        ids = [m.get("id", "") for m in (data.get("data") or [])[:5]]
        print("OK: key accepted. Sample model ids:", ids)
        print("RESULT: Key is SET and ALLOWED by the API.")
    elif r.status_code == 401:
        print("Body snippet:", r.text[:200])
        print("RESULT: Key is SET but REJECTED (401). Revoke and create a new key.")
        raise SystemExit(2)
    else:
        print("Body snippet:", r.text[:300])
        print("RESULT: Unexpected response (check base URL / provider).")
        raise SystemExit(3)


if __name__ == "__main__":
    main()
