"""
Coolio **observation memory** — lightweight, on-disk recap of recent open-web pulls.

This is **not** online fine-tuning of a neural net; it appends short text summaries
so later LLM calls can see what Coolio already fetched on this machine (RAG-style).
Bounded file size; safe for air-gapped review (plain JSONL under ``data/coolio_memory/``).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from .project_paths import PROJECT_ROOT

MEMORY_DIR = PROJECT_ROOT / "data" / "coolio_memory"
OBSERVATIONS_FILE = MEMORY_DIR / "observations.jsonl"
_MAX_BYTES = int(os.getenv("EPFORECAST_COOLIO_MEMORY_MAX_BYTES", str(2_000_000)))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def coolio_memory_enabled() -> bool:
    return os.getenv("EPFORECAST_COOLIO_MEMORY", "1").strip().lower() not in ("0", "false", "no")


def append_coolio_observation(
    *,
    disease: str | None,
    summary: str,
    source_count: int = 0,
) -> None:
    """Record one observation line (trimmed). Fails silently if disk not writable."""
    if not coolio_memory_enabled():
        return
    try:
        summary = (summary or "").strip()
        if not summary and len(str(disease or "").strip()) < 2:
            return
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": _utc_iso(),
            "disease": (disease or "").strip()[:120],
            "source_count": int(source_count),
            "summary": summary[:1200],
        }
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with open(OBSERVATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        _maybe_trim_file()
    except Exception:
        pass


def _maybe_trim_file() -> None:
    if not OBSERVATIONS_FILE.exists():
        return
    try:
        if OBSERVATIONS_FILE.stat().st_size <= _MAX_BYTES:
            return
        lines = OBSERVATIONS_FILE.read_text(encoding="utf-8").splitlines()
        keep = lines[-(len(lines) // 2 or 5000) :]
        OBSERVATIONS_FILE.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    except Exception:
        pass


def recent_memory_for_prompt(
    *,
    disease: str | None,
    max_lines: int = 14,
    max_chars: int = 2400,
) -> str:
    """Return a compact block for LLM context (newest last)."""
    if not coolio_memory_enabled():
        return ""
    if not OBSERVATIONS_FILE.exists():
        return ""
    try:
        raw = OBSERVATIONS_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    if not raw:
        return ""
    dkey = (disease or "").strip().casefold()
    rows: list[str] = []
    for line in raw[-800:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        dis = str(obj.get("disease") or "").strip().casefold()
        if dkey and dis and dkey not in ("all diseases", "all") and dis != dkey:
            continue
        ts = str(obj.get("ts") or "")
        sm = str(obj.get("summary") or "").strip()
        if sm:
            rows.append(f"- {ts} · {sm}")
    if not rows:
        return ""
    tail = rows[-max_lines:]
    text = "\n".join(tail)
    if len(text) > max_chars:
        text = text[-max_chars:]
    return "Prior Coolio observations on this install (open-web pulls, newest at bottom):\n" + text
