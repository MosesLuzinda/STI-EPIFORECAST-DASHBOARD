# Data directory

Runtime and validated datasets used by **Pathogen Economy Epiforecast**:

| Path | Purpose |
|------|---------|
| `signals.db` | SQLite store of AI-validated outbreak signals (default; override with `SIGNAL_DB_PATH` in `.env`). |

The app resolves relative paths against the **repository root**, not the current working directory, so Streamlit and FastAPI share the same database when run from this project.

Add export snapshots, CSV reference files, or backup dumps here as needed; keep secrets and large binaries out of git (see `.gitignore`).
