"""
Shim so `streamlit run app.py` from the repository root still works.
The live application lives in `frontend/app.py`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

_frontend = ROOT / "frontend" / "app.py"
_spec = importlib.util.spec_from_file_location("pef_streamlit_app", _frontend)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Cannot load frontend app: {_frontend}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["pef_streamlit_app"] = _mod
_spec.loader.exec_module(_mod)
