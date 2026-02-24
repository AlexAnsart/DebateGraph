# DebateGraph — Test Results Report

**Date:** 2026-02-23  
**Audio:** `demos/obama_romney_10min.mp3` (9.2 MB, 600s — 2012 Obama/Romney Town Hall debate excerpt)  
**Tests run:** 2 full end-to-end pipeline runs with real API calls (no mocks)

---

## Summary

Both pipeline runs completed successfully with real API calls to OpenAI (transcription), Anthropic Claude (claim extraction + fallacy detection + fact-check synthesis), and Tavily (web search for fact-checking). All results are persisted to PostgreSQL and accessible via the REST API and DB viewer.

---

## Run 1 — Initial Test

**Job ID:** `c6171ad4-9e9b-4304-8062-bd6ec3ac358c`  
**Total time:** 486s (8.1 min)

| Stage | Time | Result |
|-------|------|--------|
| Transcription (OpenAI gpt-4o-transcribe-diarize) | 262s | 177 segments, 5 speakers |
| Claim extraction (Claude claude-3-haiku-20240307) | 56s | 147 nodes, 91 edges |
| Fallacy detection (Claude + structural) | 12s | 23 fallacies |
| Fact-checking (Tavily + Claude) | 153s | 78 fact-checks |
| **Total analysis** | **223s** | |

### Graph Statistics
- **Nodes (claims):** 147
- **Edges (relations):** 91
- **Fallacies detected:** 23
- **Fact-checks completed:** 78
- **Cycles detected:** 0

### Rigor Scores
| Speaker | Score | Fallacies | Fact-check Rate |
|---------|-------|-----------|-----------------|
| SPEAKER_03 (moderator) | 63.7% | 0 | 50% |
| SPEAKER_31 (audience) | 60.0% | 0 | 0% |
| SPEAKER_28 (moderator) | 49.2% | 4 | 50% |
| SPEAKER_54 (Obama) | 29.0% | 8 | 20.5% |
| SPEAKER_41 (Romney) | 26.4% | 11 | 6.1% |

### Fallacy Breakdown
| Type | Count |
|------|-------|
| strawman | 6 |
| hasty_generalization | 5 |
| goal_post_moving | 3 |
| circular_reasoning | 3 |
| false_dilemma | 2 |
| slippery_slope | 2 |
| appeal_to_authority | 1 |
| appeal_to_emotion | 1 |

### Fact-Check Verdicts
| Verdict | Count |
|---------|-------|
| partially_true | 47 |
| unverifiable | 16 |
| supported | 11 |
| refuted | 4 |

### Issues Found (Fixed in Run 2)
1. **Noise segments:** Short fragments ("actually,", "I'm I'm", "House") were being extracted as claims
2. **Invalid relation types:** LLM occasionally returned `"conclusion"` or `"rebuttal"` as relation types (should be `"support"`, `"attack"`, etc.)
3. **Fallacy type normalization:** LLM returned `"straw_man"` instead of `"strawman"`
4. **JSON parse errors:** Apostrophes in claim text caused JSON decode failures in researcher
5. **Unicode logging:** Windows cp1252 console couldn't display ✓ ✗ → symbols
6. **DB viewer datetime bug:** `job["created_at"]` was a `datetime` object, not a string

---

## Run 2 — Improved Test (After Fixes)

**Job ID:** `279c1fb2-e84a-4f5e-86b7-c2c789d41ccf`  
**Total time:** 423s (7.1 min) — **15% faster**

| Stage | Time | Result |
|-------|------|--------|
| Transcription (OpenAI gpt-4o-transcribe-diarize) | 254s | 165 segments, 4 speakers |
| Noise filtering | <1s | 22 segments filtered (165→143) |
| Claim extraction (Claude claude-3-haiku-20240307) | 49s | 111 nodes, 85 edges |
| Fallacy detection (Claude + structural) | 9s | 16 fallacies |
| Fact-checking (Tavily + Claude) | 109s | 73 fact-checks |
| **Total analysis** | **169s** | |

### Graph Statistics
- **Nodes (claims):** 111 (cleaner — noise filtered)
- **Edges (relations):** 85
- **Fallacies detected:** 16
- **Fact-checks completed:** 73
- **Cycles detected:** 0

### Rigor Scores
| Speaker | Score | Fallacies | Fact-check Rate |
|---------|-------|-----------|-----------------|
| SPEAKER_48 (audience) | 80.0% | 0 | 0% |
| SPEAKER_00 (moderator) | 54.2% | 3 | 50% |
| SPEAKER_66 (Romney) | 33.1% | 7 | 11.8% |
| SPEAKER_14 (Obama) | 31.8% | 6 | 28.9% |

### Fallacy Breakdown
| Type | Count |
|------|-------|
| false_dilemma | 4 |
| slippery_slope | 4 |
| goal_post_moving | 2 |
| strawman | 2 |
| hasty_generalization | 2 |
| appeal_to_emotion | 1 |
| appeal_to_authority | 1 |

### Fact-Check Verdicts
| Verdict | Count |
|---------|-------|
| partially_true | 43 |
| supported | 15 |
| unverifiable | 10 |
| refuted | 5 |

### Top Fallacies (by severity)
1. **[Obama] false_dilemma (0.70)** — "we're going to pay for it, but we can't tell you until maybe after the election how we're going to do it"  
   *Q: What other options might exist to provide a clear plan for how the proposed spending will be funded?*

2. **[Romney] slippery_slope (0.70)** — "That's math that doesn't add up."  
   *Q: What specific evidence connects the deficit numbers to the broader claim about the math not adding up?*

3. **[Romney] slippery_slope (0.70)** — "This puts us on a road to Greece"  
   *Q: What evidence supports the claim that increasing national debt will lead to the same outcome as Greece?*

4. **[Moderator] false_dilemma (0.70)** — "But I will get run out if I don't"  
   *Q: What other possible courses of action could the speaker consider?*

5. **[Romney] appeal_to_authority (0.70)** — "let's have a flexible schedule so you can have hours that work for you"  
   *Q: What additional evidence would be needed to justify this policy recommendation?*

---

## Fixes Applied

### 1. `backend/api/routes/ws.py` — WebSocket stale import
**Problem:** `from api.routes.upload import jobs` referenced a deleted in-memory dict  
**Fix:** Replaced with `from db.database import get_job` — now polls PostgreSQL for job status

### 2. `backend/agents/ontological.py` — Noise segment filtering
**Problem:** Very short segments ("actually,", "I'm I'm", "House") were sent to LLM and extracted as meaningless claims  
**Fix:** Added `_filter_segments()` method that skips segments with <4 words that are filler words. Filtered 22/165 segments in Run 2.

### 3. `backend/config/settings.py` — Prompt engineering
**Problem:** LLM returned invalid relation types (`"conclusion"`, `"rebuttal"`, `"example"`) instead of valid ones  
**Fix:** Added explicit `CRITICAL RULES` section to `ONTOLOGICAL_EXTRACTION_PROMPT` clarifying that relation types and claim types are separate enums and must not be mixed

### 4. `backend/agents/skeptic.py` — Fallacy type normalization
**Problem:** LLM returned `"straw_man"` (with underscore) instead of `"strawman"`  
**Fix:** Added `_fallacy_aliases` dict mapping common LLM variations to canonical enum values

### 5. `backend/agents/researcher.py` — JSON parse robustness
**Problem:** Apostrophes in claim text (e.g., "she couldn't bring suit") caused JSON decode failures  
**Fix:** Added `_safe_parse_json()` method with fallback repair strategies including smart quote normalization and regex-based field extraction

### 6. `backend/api/routes/dbviewer.py` — datetime serialization bug
**Problem:** `job["created_at"]` returned as `datetime.datetime` object from psycopg2, but code tried to slice it with `[:19]`  
**Fix:** Added `hasattr(_created_raw, 'isoformat')` check to convert datetime objects to ISO strings before slicing

### 7. `backend/api/routes/upload.py` — Route ordering for `/snapshot/latest`
**Problem:** `/api/snapshot/{job_id}` route caught `/api/snapshot/latest` before the dedicated endpoint in `main.py`  
**Fix:** Added explicit `/api/snapshot/latest` route to `upload.py` router BEFORE the `{job_id}` route

---

## Database State

### PostgreSQL Tables
```
jobs (2 rows):
  279c1fb2 | complete | obama_romney_10min.mp3 | nodes=111 edges=85 fallacies=16 factchecks=73
  c6171ad4 | complete | obama_romney_10min.mp3 | nodes=147 edges=91 fallacies=23 factchecks=78

graph_snapshots (2 rows):
  669dd004 | job=279c1fb2 | 111 nodes, 85 edges, 16 fallacies, 73 factchecks
  fe097cdf | job=c6171ad4 | 147 nodes, 91 edges, 23 fallacies, 78 factchecks
```

### Data Stored Per Snapshot
- Full `snapshot_json` (JSONB): all nodes with claim text, type, speaker, timestamps, confidence, factcheck verdict + explanation + sources, fallacy annotations + socratic questions
- Full `transcription_json` (JSONB): all 165/177 segments with speaker, text, start/end timestamps
- Metadata: num_nodes, num_edges, num_fallacies, num_factchecks, speakers array

---

## API Endpoints (All Verified Working)

| Endpoint | Method | Status | Description |
|----------|--------|--------|-------------|
| `/api/health` | GET | ✅ | Health check with API key status |
| `/api/upload` | POST | ✅ | Upload audio file, start pipeline |
| `/api/status/{job_id}` | GET | ✅ | Job status + snapshot when complete |
| `/api/jobs` | GET | ✅ | List all jobs with metadata |
| `/api/snapshot/latest` | GET | ✅ | Most recent completed snapshot |
| `/api/snapshot/{job_id}` | GET | ✅ | Specific job snapshot |
| `/api/demo` | POST | ✅ | Run demo pipeline (no audio needed) |
| `/db` | GET | ✅ | DB viewer HTML (dark theme, auto-refresh) |
| `/db/snapshot/{job_id}` | GET | ✅ | Full snapshot detail with all tables |
| `/ws/{job_id}` | WS | ✅ | Real-time job status streaming |

---

## Frontend Integration

The frontend can load graphs from the DB via:
1. **UploadPanel** → "Load from Database" section → lists all completed jobs → "Load Graph" button
2. **URL parameter:** `http://localhost:5173/?job={job_id}` (linked from DB viewer)
3. **Latest snapshot:** `GET /api/snapshot/latest` (used by "Load Latest" button)

All graph data visible in frontend:
- **GraphView:** Cytoscape.js graph with nodes colored by speaker, shaped by claim type, bordered by fallacy/factcheck status
- **NodeDetail:** Full claim text, factcheck verdict + explanation + sources, all fallacy annotations + socratic questions
- **FallacyPanel:** All fallacies with severity badges and socratic questions
- **RigorScore:** Per-speaker composite scores with breakdown
- **WaveformView:** Audio waveform + synchronized transcript with speaker colors

---

## DB Viewer

Available at `http://localhost:8000/db`:
- Jobs table with status badges, metadata, links to frontend and JSON viewer
- Snapshots table with node/edge/fallacy/factcheck counts
- Snapshot detail page (`/db/snapshot/{job_id}`) with:
  - Rigor scores table
  - Fallacies table (type, severity, explanation, socratic question)
  - Nodes/Claims table (ID, speaker, type, text, timestamp, factual flag, verdict, FC explanation, fallacy count)
  - Edges/Relations table (source, target, type, confidence)
  - Raw JSON viewer (collapsible, snapshot + transcription)
  - "Open in Frontend" button

---

## Known Remaining Issues

1. **Speaker ID normalization:** OpenAI returns different speaker IDs on each run (SPEAKER_28/54/41 vs SPEAKER_00/14/66) — this is expected behavior from the diarization model, not a bug. Speaker identities are consistent within a single run.

2. **Some noise claims still extracted:** Despite filtering, some very short but non-filler segments (e.g., "I just described", "to the extent any governor does") are still extracted as claims. These are valid speech fragments but lack argumentative content. Could be improved with a minimum word count threshold of 6-8 words.

3. **Duplicate logging:** The orchestrator logs each message twice (once to console, once to session file). This is because `setup_session_logging()` adds a handler to the root logger which already has a console handler. Non-critical.

4. **`duration_s` not set:** The `duration_s` field in the jobs table is always `null` because the audio duration is not extracted during the pipeline. Could be added using `get_audio_duration()` from `utils/audio.py`.

5. **LLM model fallback:** `LLM_MODEL_FALLBACK = "claude-haiku-4-5"` — this model name may not be valid. The primary model `claude-3-haiku-20240307` worked reliably in both runs, so the fallback was never triggered.

---

## API Call Statistics (Run 2)

| API | Calls | Purpose |
|-----|-------|---------|
| OpenAI gpt-4o-transcribe-diarize | 1 | Full audio transcription + diarization |
| Anthropic claude-3-haiku-20240307 | 15 | Claim extraction (15 chunks) |
| Anthropic claude-3-haiku-20240307 | 8 | Fallacy detection (8 chunks of 15 claims) |
| Tavily search | 73 | Web search for each factual claim |
| Anthropic claude-3-haiku-20240307 | ~65 | Verdict synthesis (some failed JSON parse) |
| **Total** | **~162** | |

---

## How to Load a Graph in the Frontend

1. Start the backend: `cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000`
2. Start the frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173`
4. In the left panel, click **"Load from Database"** to expand the job list
5. Select any completed job and click **"Load Graph"**
6. The graph will render in the center panel with all annotations

Alternatively, navigate directly to `http://localhost:5173/?job={job_id}` with a specific job ID.

The DB viewer at `http://localhost:8000/db` provides a complete view of all data in the database with links to load graphs in the frontend.
