# AGENTS.md

## Cursor Cloud specific instructions

### Services overview

| Service | Port | Command |
|---------|------|---------|
| Backend (FastAPI) | 8010 | `cd backend && source venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload` |
| Frontend (Vite) | 5173 | `cd frontend && npm run dev` |
| PostgreSQL | 5432 | `sudo pg_ctlcluster 16 main start` |

### Important caveats

- The `api/models/schemas.py` file was missing from the repo and had to be recreated from TypeScript types and import signatures. If backend fails with `ModuleNotFoundError: No module named 'api.models'`, verify this file exists at `backend/api/models/schemas.py`.
- The backend uses `requirements-dev.txt` for lightweight dev mode (no WhisperX/sentence-transformers). For full pipeline with LLM analysis, install `requirements.txt` and set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` in `.env`.
- PostgreSQL is optional; the backend degrades gracefully without it (`db_available=False`). The "Load from Database" feature requires it.
- `.env` must be created from `.env.example` at the repo root. `DATABASE_URL=postgresql://debategraph:debategraph@localhost:5432/debategraph` for local dev.
- The demo endpoint (`POST /api/demo`) works without any API keys but does not persist to database. To seed demo data for the "Load from Database" feature, a manual insert is needed.
- The root `package.json` contains Windows-specific `sharp` dependencies that are not needed on Linux and can be ignored.
- Frontend proxies `/api` and `/ws` to `localhost:8010` via Vite config, so both services must run simultaneously.

### Lint / Build / Test

- **Frontend lint/build**: `cd frontend && npx tsc --noEmit` (type-check) and `npm run build`
- **Backend**: No linter or test runner is configured in the repo. Run `python -m pytest` if tests are added.
- **Frontend dev server**: `cd frontend && npm run dev` (Vite on port 5173)
