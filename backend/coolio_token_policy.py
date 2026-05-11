"""How Coolio passes ``max_tokens`` to OpenAI-compatible providers."""
from __future__ import annotations

import os


def coolio_max_tokens_from_env(env_var: str, *, default: int | None = None) -> int | None:
    """
    - ``0``, ``-1``, ``none``, ``unlimited``, ``omit`` → omit (``None``) so the provider decides.
    - unset → ``default``.
    - positive int → cap.
    """
    raw = (os.getenv(env_var) or "").strip().lower()
    if raw in ("0", "-1", "none", "unlimited", "omit"):
        return None
    if raw == "":
        return default
    try:
        v = int(raw)
        return None if v <= 0 else v
    except ValueError:
        return default
