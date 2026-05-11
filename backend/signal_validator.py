"""
AI-powered signal validator.

Decides whether a candidate feed item (RSS / GDELT / Reddit / HN / etc.)
is a real disease-outbreak signal before it is counted by the dashboard
or fed into the signal-trained forecast model.

Pipeline per item:
  1. Cheap keyword pre-filter against the disease/outbreak vocabulary.
     Items with no keyword hit are rejected without spending an LLM call.
  2. Items that pass the keyword filter are batched and sent to the LLM
     for a structured JSON decision (is_signal, disease, location, reason).
  3. Decisions are cached by URL/title hash so subsequent refreshes are
     free for already-seen items.
  4. A per-window LLM call budget protects against runaway cost; when the
     budget is exhausted we fall back to the keyword decision.

Public API:
    validate_signals_batch(items)  -> list[dict]  (aligned with input order)
    keyword_relevant(text)         -> bool        (cheap filter for counters)

Each decision dict has the shape:
    {
        "is_signal": bool,
        "confidence": float,        # 0.0 - 1.0
        "disease":   str,           # may be empty
        "location":  str,           # may be empty
        "reason":    str,
        "engine":    "cache" | "llm" | "keyword",
    }

Configuration (env vars, all optional):
    SIGNAL_VALIDATOR_MAX_LLM_CALLS    default 30  (per ~60s window)
    SIGNAL_VALIDATOR_CACHE_TTL_SEC    default 86400
    SIGNAL_VALIDATOR_LLM_TIMEOUT      default 20
    SIGNAL_VALIDATOR_BATCH_SIZE       default 8
    CURSOR_API_KEY / AI_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / GOOGLE_AI_API_KEY / XAI_API_KEY
    CURSOR_API_BASE_URL / AI_BASE_URL / OPENAI_BASE_URL
    CURSOR_AI_MODEL / AI_MODEL
    AI_FAILOVER_API_KEY / GROQ_API_KEY  (optional Groq failover)
    AI_FAILOVER_BASE_URL / GROQ_BASE_URL (optional; default Groq OpenAI-compatible host)
    AI_FAILOVER_MODEL / GROQ_MODEL       (optional; defaults per host)

    Zero-cost mode: LOCAL_LLM_URL or OLLAMA_BASE_URL (see backend/ai_config.py)
    SIGNAL_VALIDATOR_UGANDA_LOCALITIES  default 1 — heuristic place hints (e.g. Kampala)
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Iterable

import requests

from .ai_config import llm_openai_compatible_chain
from .statistical_forecast import OUTBREAK_KEYWORDS as _OUTBREAK_KEYWORDS


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


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, str(int(default)))).strip().lower()
    return value in {"1", "true", "yes", "on"}


_DEFAULT_BUDGET = _env_int("SIGNAL_VALIDATOR_MAX_LLM_CALLS", 30)
_CACHE_TTL_SEC = _env_int("SIGNAL_VALIDATOR_CACHE_TTL_SEC", 86_400)
# Default kept under the data_services as_completed(timeout=15) deadline so
# one batch call per items-fetcher stays within the live feed refresh window.
_LLM_TIMEOUT_SEC = _env_float("SIGNAL_VALIDATOR_LLM_TIMEOUT", 11.0)
_BATCH_SIZE = max(1, _env_int("SIGNAL_VALIDATOR_BATCH_SIZE", 10))
_MAX_PENDING_ITEMS = max(1, _env_int("SIGNAL_VALIDATOR_MAX_PENDING_ITEMS", 120))
_DISABLE_LLM = _env_bool("SIGNAL_VALIDATOR_DISABLE_LLM", False) or _env_bool("EPFORECAST_NO_AI", False)
_BUDGET_WINDOW_SEC = 60.0
_MIN_ACCEPT_CONFIDENCE = max(0.0, min(1.0, _env_float("SIGNAL_VALIDATOR_MIN_ACCEPT_CONFIDENCE", 0.35)))
_MAX_CACHE_ENTRIES = max(200, _env_int("SIGNAL_VALIDATOR_MAX_CACHE_ENTRIES", 5000))
_HTTP_SESSION = requests.Session()

# Longer phrases first so "fort portal" wins over "tororo".
_UGANDA_PLACE_LABELS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            ("fort portal", "Fort Portal"),
            ("kira municipality", "Kira"),
            ("kampala", "Kampala"),
            ("mbarara", "Mbarara"),
            ("gulu", "Gulu"),
            ("jinja", "Jinja"),
            ("entebbe", "Entebbe"),
            ("lira", "Lira"),
            ("mbale", "Mbale"),
            ("mubende", "Mubende"),
            ("kasese", "Kasese"),
            ("arua", "Arua"),
            ("soroti", "Soroti"),
            ("tororo", "Tororo"),
            ("hoima", "Hoima"),
            ("mukono", "Mukono"),
            ("wakiso", "Wakiso"),
            ("nansana", "Nansana"),
            ("busia", "Busia"),
            ("iganga", "Iganga"),
            ("kabale", "Kabale"),
            ("masaka", "Masaka"),
            ("moroto", "Moroto"),
            ("kotido", "Kotido"),
            ("adjumani", "Adjumani"),
            ("apac", "Apac"),
            ("bundibugyo", "Bundibugyo"),
            ("kamuli", "Kamuli"),
            ("kayunga", "Kayunga"),
            ("luweero", "Luweero"),
            ("mpigi", "Mpigi"),
            ("mityana", "Mityana"),
            ("nakaseke", "Nakaseke"),
            ("nakasongola", "Nakasongola"),
            ("pader", "Pader"),
            ("rukungiri", "Rukungiri"),
            ("sembabule", "Sembabule"),
            ("nebbi", "Nebbi"),
            ("paidha", "Paidha"),
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)


def _infer_uganda_locality(text: str) -> str:
    if not _env_bool("SIGNAL_VALIDATOR_UGANDA_LOCALITIES", True):
        return ""
    lower = (text or "").lower()
    if not lower:
        return ""
    for needle, label in _UGANDA_PLACE_LABELS:
        if needle in lower:
            return label
    return ""


def _merge_locality(decision: dict, text: str) -> None:
    if str(decision.get("location") or "").strip():
        return
    hint = _infer_uganda_locality(text)
    if hint:
        decision["location"] = hint


_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_budget_lock = threading.Lock()
_budget_state: dict[str, float] = {"calls": 0.0, "window_start": time.time()}


def _hash_key(item: dict) -> str:
    base = (item.get("url") or "").strip()
    if not base:
        base = (item.get("title") or "").strip().lower()
    return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()


def _keyword_decision(text: str) -> tuple[bool, str | None]:
    if not text:
        return False, None
    lower = text.lower()
    for kw in _OUTBREAK_KEYWORDS:
        if kw in lower:
            return True, kw
    return False, None


def keyword_relevant(text: str) -> bool:
    """Cheap keyword filter retained for high-volume count functions."""
    return _keyword_decision(text)[0]


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > _CACHE_TTL_SEC:
            _cache.pop(key, None)
            return None
        result = dict(value)
    result["engine"] = "cache"
    return result


def _cache_set(key: str, value: dict) -> None:
    with _cache_lock:
        if len(_cache) >= _MAX_CACHE_ENTRIES:
            # Drop oldest entries to cap memory growth in long-lived processes.
            overflow = len(_cache) - _MAX_CACHE_ENTRIES + 1
            for k in list(_cache.keys())[:overflow]:
                _cache.pop(k, None)
        _cache[key] = (time.time(), dict(value))


def _budget_take() -> bool:
    """Consume one LLM-call slot from the rolling window. False if exhausted."""
    with _budget_lock:
        now = time.time()
        if now - _budget_state["window_start"] > _BUDGET_WINDOW_SEC:
            _budget_state["calls"] = 0
            _budget_state["window_start"] = now
        if _budget_state["calls"] >= _DEFAULT_BUDGET:
            return False
        _budget_state["calls"] += 1
        return True


_SYSTEM_PROMPT = (
    "You validate news / social items for a disease-outbreak surveillance "
    "dashboard. For each item, decide whether it is a REAL disease-outbreak "
    "signal (active outbreak, cluster of cases, surveillance alert, surge, "
    "public-health emergency, line list, suspected cases). Items about "
    "historical retrospectives, vaccine launches without an active outbreak, "
    "policy announcements without case data, opinion / commentary, or "
    "unrelated topics are NOT signals. "
    "Return ONLY valid JSON: an array aligned with the input index 'i'. "
    "Each object MUST have keys: i (int), is_signal (bool), confidence "
    "(float 0..1), disease (string or empty), location (string or empty), "
    "reason (short string)."
)


from .json_extract import strip_markdown_fence as _strip_code_fence  # shared helper


def _llm_classify_batch(items: list[dict]) -> list[dict | None] | None:
    payload_items = [
        {
            "i": idx,
            "source": str(it.get("source") or "")[:40],
            "title": str(it.get("title") or "")[:300],
            "description": str(
                it.get("description") or it.get("meta") or ""
            )[:400],
        }
        for idx, it in enumerate(items)
    ]
    user_prompt = "Items:\n" + json.dumps(payload_items, ensure_ascii=False)
    json_body = {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }

    for api_key, base_url, model in llm_openai_compatible_chain():
        body = dict(json_body)
        body["model"] = model
        try:
            response = _HTTP_SESSION.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=_LLM_TIMEOUT_SEC,
            )
            if response.status_code != 200:
                continue
            text = response.json()["choices"][0]["message"]["content"]
            data = json.loads(_strip_code_fence(text))
        except Exception:
            continue

        if not isinstance(data, list):
            continue

        out: list[dict | None] = [None] * len(items)
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("i"))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(items):
                continue
            try:
                confidence = float(entry.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            row = {
                "is_signal": bool(entry.get("is_signal")),
                "confidence": max(0.0, min(1.0, confidence)),
                "disease": str(entry.get("disease") or "").strip()[:60],
                "location": str(entry.get("location") or "").strip()[:120],
                "reason": str(entry.get("reason") or "").strip()[:240],
                "engine": "llm",
            }
            it = items[idx]
            blob = " ".join(
                [
                    str(it.get("title") or ""),
                    str(it.get("description") or ""),
                    str(it.get("meta") or ""),
                ]
            )
            _merge_locality(row, blob)
            out[idx] = row
        return out

    return None


def _apply_acceptance_policy(decision: dict) -> dict:
    """Normalize low-confidence positives to reduce noisy false alerts."""
    out = dict(decision or {})
    is_signal = bool(out.get("is_signal"))
    try:
        confidence = float(out.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    out["confidence"] = confidence
    if is_signal and confidence < _MIN_ACCEPT_CONFIDENCE:
        out["is_signal"] = False
        out["reason"] = f"below confidence threshold ({_MIN_ACCEPT_CONFIDENCE:.2f})"
    return out


def validate_signals_batch(items: Iterable[dict]) -> list[dict]:
    """
    Validate a batch of candidate feed items in input order.

    Each returned dict has: is_signal, confidence, disease, location,
    reason, engine. The list length matches the number of input items.
    """
    items_list = list(items)
    decisions: list[dict] = [
        {
            "is_signal": False, "confidence": 0.0, "disease": "",
            "location": "", "reason": "no decision", "engine": "keyword",
        }
        for _ in items_list
    ]
    pending_indices: list[int] = []
    pending_by_hash: dict[str, list[int]] = {}

    for idx, item in enumerate(items_list):
        key = _hash_key(item)
        cached = _cache_get(key)
        if cached is not None:
            decisions[idx] = cached
            continue
        text = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("description") or ""),
                str(item.get("meta") or ""),
            ]
        )
        kw_hit, kw_match = _keyword_decision(text)
        decisions[idx] = {
            "is_signal": bool(kw_hit),
            "confidence": 0.55 if kw_hit else 0.10,
            "disease": (kw_match or "").strip(),
            "location": "",
            "reason": "keyword pre-filter" if kw_hit else "no keyword match",
            "engine": "keyword",
        }
        _merge_locality(decisions[idx], text)
        if kw_hit:
            pending_indices.append(idx)
            pending_by_hash.setdefault(key, []).append(idx)

    if _DISABLE_LLM:
        for idx, item in enumerate(items_list):
            _cache_set(_hash_key(item), decisions[idx])
        return decisions

    # Deduplicate within a batch (same url/title often appears across feeds),
    # then cap work to protect response time/cost.
    unique_pending: list[int] = []
    seen_pending_hashes: set[str] = set()
    for idx in pending_indices:
        h = _hash_key(items_list[idx])
        if h in seen_pending_hashes:
            continue
        seen_pending_hashes.add(h)
        unique_pending.append(idx)
    trimmed_pending = unique_pending[:_MAX_PENDING_ITEMS]

    for batch_start in range(0, len(trimmed_pending), _BATCH_SIZE):
        chunk = trimmed_pending[batch_start:batch_start + _BATCH_SIZE]
        if not chunk:
            break
        if not _budget_take():
            break
        batch_items = [items_list[i] for i in chunk]
        results = _llm_classify_batch(batch_items)
        if not results:
            continue
        for offset, result in enumerate(results):
            if result is None:
                continue
            normalized = _apply_acceptance_policy(result)
            primary_idx = chunk[offset]
            decisions[primary_idx] = normalized
            # Mirror result to duplicate items in the same batch.
            for dup_idx in pending_by_hash.get(_hash_key(items_list[primary_idx]), []):
                decisions[dup_idx] = dict(normalized)

    for idx, item in enumerate(items_list):
        blob = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("description") or ""),
                str(item.get("meta") or ""),
            ]
        )
        _merge_locality(decisions[idx], blob)
        decisions[idx] = _apply_acceptance_policy(decisions[idx])
        _cache_set(_hash_key(item), decisions[idx])

    return decisions
