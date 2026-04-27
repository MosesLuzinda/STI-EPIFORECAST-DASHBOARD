"""Check .env API key is set and accepted (no secrets printed)."""
from pathlib import Path

from dotenv import load_dotenv
import os
import requests

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def mask(s: str) -> str:
    if not s:
        return "(not set)"
    s = s.strip()
    if len(s) <= 8:
        return s[:2] + "..." + s[-2:]
    return s[:4] + "..." + s[-4:]


def main() -> None:
    keys = [
        ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
        ("CURSOR_API_KEY", os.getenv("CURSOR_API_KEY")),
        ("AI_API_KEY", os.getenv("AI_API_KEY")),
        ("XAI_API_KEY", os.getenv("XAI_API_KEY")),
    ]
    base = (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("AI_BASE_URL")
        or os.getenv("CURSOR_API_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = os.getenv("AI_MODEL") or os.getenv("CURSOR_AI_MODEL") or "gpt-4o-mini"

    print("--- Environment (masked) ---")
    for name, val in keys:
        if val and val.strip():
            print(f"{name}: SET  value: {mask(val)}")
        else:
            print(f"{name}: NOT SET")

    print("Base URL:", base)
    print("Model:", model)

    raw = None
    used = None
    for name, val in keys:
        if val and val.strip():
            raw = val.strip()
            used = name
            break

    if not raw:
        print()
        print("RESULT: No API key found. Add OPENAI_API_KEY (or similar) to .env")
        raise SystemExit(1)

    url = f"{base}/models"
    r = requests.get(url, headers={"Authorization": f"Bearer {raw}"}, timeout=15)
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
