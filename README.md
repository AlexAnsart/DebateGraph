# DebateGraph

**Real-Time Argumentative Analysis Engine — From Speech to Structured Logic**

DebateGraph transforms audio/video debates into interactive argument graphs. It combines speech-to-text with speaker diarization, LLM-powered claim extraction, automated fallacy detection, asynchronous fact-checking, and dynamic graph visualization.

> **Epistemic co-pilot**: the system structures, verifies, and questions arguments — while leaving interpretation to the user.

---

**Launch Frontend and Backend via Docker Compose**
docker-compose up -d

Frontend: http://localhost:3000
Backend: http://localhost:8000
PostgreSQL: localhost:5432 (debategraph/debategraph)
Redis: localhost:6379

**Local Development**

Backend (full stack: FastAPI + WhisperX + sentence-transformers, etc.):
```bash
cd backend
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
**Windows — full stack without a C compiler:** Use **Python 3.12** (not 3.13). Under 3.13, numpy has no wheel and would need a build; WhisperX/pyannote expect numpy 1.x. Create the venv with 3.12, then use the venv Python so pip and the reload subprocess use it:
```powershell
# In backend\, with Python 3.12 on PATH (e.g. py -3.12 -m venv venv if you have both):
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# Or: .\run.ps1
```
If you stay on Python 3.13 and don't install Build Tools, use `requirements-core.txt` to run the app (demo mode, API) without WhisperX.

Frontend (other terminal):
```bash
cd frontend
npm install
npm run dev
```

---

## Features

| Feature | Description | Status |
|---------|-------------|--------|
| 🎙️ **Speech-to-Text + Diarization** | OpenAI `gpt-4o-transcribe-diarize` for transcription with speaker attribution | ✅ |
| 🧠 **Claim Extraction** | Claude API extracts atomic claims, types (premise/conclusion/rebuttal/concession), and relations | ✅ |
| 🔗 **Argument Graph** | Directed graph of claims with support/attack/undercut/reformulation/implication edges | ✅ |
| 🎯 **Fallacy Detection** | Structural (cycles, strawman, goalpost) + LLM-based detection of 12 fallacy types | ✅ |
| ✅ **Fact-Checking** | Tavily web search + Claude verdict synthesis for factual claims | ✅ |
| 📊 **Rigor Scores** | Composite per-speaker score (supported ratio, fallacy penalty, fact-check rate, consistency) | ✅ |
| 🌐 **Interactive Graph** | Cytoscape.js visualization with color-coded speakers, relation types, and fallacy highlights | ✅ |
| 🔊 **Waveform View** | WaveSurfer.js audio waveform with synchronized transcript | ✅ |
| ⚡ **Demo Mode** | Hardcoded debate data for testing without API keys or audio files | ✅ |
| 🔄 **Rule-Based Fallback** | Works without API keys using rule-based extraction and detection | ✅ |

---

## Architecture

```
Audio/Video File
       │
       ▼
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Transcription│────▶│ Ontological Agent │────▶│  Skeptic Agent   │
│  (OpenAI STT) │     │ (Claim Extraction)│     │ (Fallacy Detect) │
└──────────────┘     └──────────────────┘     └─────────────────┘
                            │                         │
                            ▼                         ▼
                     ┌──────────────┐          ┌──────────────┐
                     │ Graph Store   │◀─────────│ Researcher   │
                     │ (NetworkX)    │          │ (Fact-Check)  │
                     └──────┬───────┘          └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  GraphSnapshot│──────▶  Frontend (React)
                     │  (JSON API)   │
                     └──────────────┘
```

### Multi-Agent Pipeline

1. **Ontological Agent** — Extracts claims from transcription, infers types and relations, builds the argument graph
2. **Skeptic Agent** — Detects fallacies via structural analysis (cycles, strawman, goalpost) + LLM classification
3. **Researcher Agent** — Fact-checks factual claims using Tavily web search + Claude verdict synthesis
4. **Orchestrator** — Coordinates agents sequentially, computes rigor scores, generates the final snapshot

---

## Docker in This Project

Docker is used to **containerize and orchestrate** the three services that make up DebateGraph in production:

| Container | Role |
|-----------|------|
| **backend** | FastAPI Python application — runs the analysis pipeline (transcription, agents, graph). Built from `backend/Dockerfile`. Exposes port 8000. |
| **frontend** | React/Vite application — serves the interactive UI. Built from `frontend/Dockerfile`. Exposes port 3000. |
| **redis** | Redis 7 (Alpine) — in-memory message broker reserved for **future real-time features** (Phase 3: WebSocket pub/sub for live streaming analysis). Currently provisioned but not actively used by the pipeline. |
| **postgres** | PostgreSQL 16 — database for persistent storage of jobs, claims, relations, fallacies, fact-checks, and LLM audit trails. |

**Why Docker?**
- **Reproducible environment**: eliminates "works on my machine" issues — Python version, system dependencies (ffmpeg), and Node.js are all pinned inside the images.
- **One-command deployment**: `docker-compose up -d` starts the entire stack (backend + frontend + Redis + PostgreSQL) with proper networking, volume mounts for logs/uploads, and environment variable injection from `.env`.
- **Isolation**: each service runs in its own container with its own dependencies. The backend's heavy Python ML/API dependencies don't interfere with the frontend's Node.js toolchain.
- **Production-ready**: the compose file includes `restart: unless-stopped`, shared volumes for persistent logs and uploads, and inter-service networking.

**You don't need Docker for local development.** You can run the backend (`python main.py`) and frontend (`npm run dev`) directly. Docker is for deployment and CI/CD.

---

## Graph System — Edge Semantics & Direction

The argument graph is a **directed graph** (NetworkX `DiGraph`) where:

- **Nodes** = individual atomic claims (one idea per node), attributed to a speaker with timestamps
- **Edges** = logical/argumentative relationships between claims

### Edge Direction Convention

Edges follow a **"source acts upon target"** convention — the direction represents the **argumentative role**, not chronological order:

| Edge Type | Direction (`source → target`) | Meaning |
|-----------|-------------------------------|---------|
| **support** | `source → target` | Source **provides evidence/reasoning for** target. The source claim supports or justifies the target claim. |
| **attack** | `source → target` | Source **contradicts or argues against** target. The source claim refutes or weakens the target claim. |
| **undercut** | `source → target` | Source **challenges the logical link** to target (attacks the inference, not the claim itself). |
| **reformulation** | `source → target` | Source **restates** target in different words (bidirectional in meaning, but stored as directed). |
| **implication** | `source → target` | Source **logically implies** target. If source is true, target follows. |

### Key Points

- **Edges are NOT chronological.** A claim made later in the debate can be the *target* of an earlier claim's support edge. The direction encodes *logical dependency*, not temporal order.
- **Timestamps are on nodes, not edges.** Each claim node carries `timestamp_start` and `timestamp_end` from the audio. To reconstruct chronological order, sort nodes by their timestamps.
- **Cross-speaker edges are common.** An attack edge typically goes from Speaker A's rebuttal to Speaker B's original claim. A support edge typically connects claims from the same speaker (premise → conclusion).
- **The graph is typically a DAG** (directed acyclic graph). Cycles indicate circular reasoning and are flagged as fallacies by the Skeptic Agent.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, NetworkX |
| **Frontend** | React 19, TypeScript, Vite 7, Tailwind CSS 4 |
| **Graph Viz** | Cytoscape.js (CoSE layout) |
| **Audio** | WaveSurfer.js, ffmpeg |
| **STT** | OpenAI `gpt-4o-transcribe-diarize` |
| **LLM** | Anthropic Claude (Haiku / Sonnet) |
| **Fact-Check** | Tavily Search API |
| **Database** | PostgreSQL 16 |
| **Deployment** | Docker, Docker Compose, Vercel-compatible frontend |

---

## How to Run DebateGraph

DebateGraph can be run in two ways: with **Docker Compose** (full stack) or **locally** (for development).

---

### Option A: Docker Compose (Recommended for production-like testing)

This starts PostgreSQL + Redis + Backend + Frontend all together.

1. **Clone & configure:**
```
bash
git clone https://github.com/your-username/DebateGraph.git
cd DebateGraph
cp .env.example .env
# Edit .env with your API keys (optional)
```

2. **Start the stack:**
```
bash
docker-compose up -d
```

**Services:**
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000
- **PostgreSQL**: localhost:5432 (`debategraph` / `debategraph`)
- **Redis**: localhost:6379

To stop:
```
bash
docker-compose down
```

---

### Option B: Local Development (Backend + Frontend on your machine)

For development with hot-reload and debug access.

#### Prerequisites

| Tool | Required | Install |
|------|----------|---------|
| Python | Yes | [python.org](https://www.python.org/downloads/) |
| Node.js | Yes | [nodejs.org](https://nodejs.org/) |
| ffmpeg | For audio processing | `choco install ffmpeg` (Windows) or `brew install ffmpeg` (macOS) |

#### Step-by-step:

**1. Clone & configure:**
```
bash
git clone https://github.com/your-username/DebateGraph.git
cd DebateGraph
cp .env.example .env
# Edit .env with your API keys if needed
```

**2. Set up Python virtual environment:**
```
bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
```

**3. Start the backend:**

From inside the `backend/` directory (with venv activated):
```
bash
python main.py
```
Or using uvicorn with hot-reload (use `python -m uvicorn` on Windows so the reload subprocess uses the venv):
```
bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
**Windows troubleshooting:** If you see "Defaulting to user installation" or `ModuleNotFoundError` in the reload process, use the venv Python explicitly: `.\venv\Scripts\python.exe -m pip install -r requirements.txt` then `.\venv\Scripts\python.exe -m uvicorn ...`. If you get **"ffmpeg not found"** on upload, install the bundled ffmpeg with the same Python that runs the server: `.\venv\Scripts\python.exe -m pip install imageio-ffmpeg` (so it installs into the venv, not user site-packages). For full stack (WhisperX) without a C compiler, use Python 3.12. If you are on 3.13 and cannot install Build Tools, use `requirements-core.txt` to run the backend without WhisperX (demo mode still works).

The backend will start at **http://localhost:8000**

**4. In another terminal, set up and start the frontend:**

```
bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:5173**

---

### Try It

1. Open **http://localhost:5173** (or http://localhost:3000 if using Docker)
2. Click **⚡ Demo** to run the built-in demo analysis (no API keys needed)
3. Or upload an audio/video file for real analysis (requires OpenAI + Anthropic keys)

---

## API Keys

| Key | Required For | Get It |
|-----|-------------|--------|
| `OPENAI_API_KEY` | Audio transcription + diarization | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Claim extraction + fallacy detection | [console.anthropic.com](https://console.anthropic.com/) |
| `TAVILY_API_KEY` | Fact-checking (web search) | [tavily.com](https://tavily.com/) (free tier: 1000 req/month) |

**Without API keys**, the system falls back to:
- Rule-based claim extraction (keyword matching)
- Rule-based fallacy detection (pattern matching)
- Mock fact-check results (all "unverifiable")

---

## Project Structure

```
DebateGraph/
├── backend/
│   ├── main.py                    # FastAPI entrypoint
│   ├── api/
│   │   ├── models/schemas.py      # Pydantic schemas (all data models)
│   │   └── routes/
│   │       ├── upload.py           # POST /api/upload, GET /api/status/:id
│   │       └── ws.py              # WebSocket endpoint (Phase 3)
│   ├── agents/
│   │   ├── orchestrator.py        # Pipeline coordinator
│   │   ├── ontological.py         # Claim extraction agent
│   │   ├── skeptic.py             # Fallacy detection agent
│   │   └── researcher.py          # Fact-checking agent
│   ├── graph/
│   │   ├── store.py               # NetworkX graph store + rigor scores
│   │   └── algorithms.py          # Cycle, strawman, goalpost, drift detection
│   ├── pipeline/
│   │   └── transcription.py       # OpenAI STT + diarization
│   ├── config/
│   │   ├── settings.py            # All configuration + LLM prompts
│   │   └── logging_config.py      # Structured session logging
│   ├── utils/
│   │   └── audio.py               # ffmpeg audio conversion
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # Main layout (3-panel + waveform)
│   │   ├── api.ts                 # API client
│   │   ├── types.ts               # TypeScript types (mirrors schemas.py)
│   │   ├── components/
│   │   │   ├── GraphView.tsx      # Cytoscape.js graph visualization
│   │   │   ├── WaveformView.tsx   # WaveSurfer.js audio + transcript
│   │   │   ├── FallacyPanel.tsx   # Fallacy list with severity badges
│   │   │   ├── FactCheckBadge.tsx # Verdict badge component
│   │   │   ├── RigorScore.tsx     # Speaker rigor score display
│   │   │   ├── NodeDetail.tsx     # Claim detail overlay
│   │   │   └── UploadPanel.tsx    # File upload + demo buttons
│   │   └── hooks/
│   │       ├── useWebSocket.ts    # WebSocket hook (Phase 3)
│   │       └── useAudioCapture.ts # Microphone capture (Phase 3)
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload audio/video file, returns `job_id` |
| `GET` | `/api/status/{job_id}` | Poll analysis status + results |
| `POST` | `/api/demo` | Run demo analysis (no file needed) |
| `GET` | `/api/snapshot/latest` | Load last pre-computed snapshot |
| `GET` | `/api/health` | Health check + feature availability |
| `GET` | `/api/jobs` | List all job IDs |
| `DELETE` | `/api/jobs/{job_id}` | Delete a job and its files |
| `WS` | `/ws/{session_id}` | Real-time updates (Phase 3) |

---

## Fact-Checking Pipeline — Complete I/O Reference

The **Researcher Agent** (`backend/agents/researcher.py`) fact-checks every claim where `is_factual=True`. The `is_factual` flag is set by the Ontological Agent: a claim is considered factual if it contains verifiable statistics, dates, named studies, or specific numerical data.

Each fact-check is a **two-step pipeline**: Tavily web search → Claude verdict synthesis.

---

### Step 1 — Tavily Web Search

**File:** `backend/agents/researcher.py` → `_check_with_tavily()`  
**Config:** `TAVILY_SEARCH_DEPTH` (default: `"advanced"`), `TAVILY_MAX_RESULTS` (default: `5`)

#### Input

| Field | Value | Example |
|-------|-------|---------|
| `query` | Claim text prefixed with `"fact check: "` | `"fact check: We've gone from $10 trillion of national debt to $16 trillion."` |
| `search_depth` | `"advanced"` (deep crawl) or `"basic"` | `"advanced"` |
| `max_results` | Max number of sources to return | `5` |
| `include_answer` | Always `True` — requests Tavily's AI-generated summary | `True` |

#### Output (raw Tavily response)

```
python
{
  "results": [
    {
      "title": "Ryan's Budget Spin - FactCheck.org",
      "url": "https://www.factcheck.org/2011/05/ryans-budget-spin/",
      "content": "...the public debt would increase from $10 trillion in 2011 to $16 trillion...",
    },
  ],
  "answer": "The U.S. national debt increased from $10 trillion to $16 trillion..."
}
```

---

### Step 2 — Claude Verdict Synthesis

**File:** `backend/agents/researcher.py` → `_synthesize_verdict()`  
**Model:** `claude-haiku-4-5` (configured via `LLM_MODEL` in `settings.py`)

#### Output (Claude JSON response)

```
json
{
  "verdict": "supported",
  "confidence": 0.9,
  "explanation": "Source 1 (FactCheck.org) confirms the public debt rose from $10T to $16T between 2009 and 2012.",
  "key_finding": "The national debt figures cited are accurate based on Treasury data."
}
```

---

### Verdict Types

| Verdict | Meaning |
|---------|---------|
| `supported` | The claim is substantially accurate based on reliable sources |
| `refuted` | The claim is clearly false or significantly misleading |
| `partially_true` | The claim contains some truth but is incomplete, exaggerated, or missing context |
| `unverifiable` | Insufficient evidence found to determine truth value |
| `pending` | Not yet checked (initial state before the agent runs) |

---

### Fallback Behavior

| Condition | Behavior |
|-----------|----------|
| No `TAVILY_API_KEY` | Returns `verdict: "unverifiable"`, `confidence: 0.3` |
| Tavily succeeds but no `ANTHROPIC_API_KEY` | Uses keyword matching on Tavily's `answer` field |
| Claude returns malformed JSON | Falls back to `verdict: "unverifiable"`, `confidence: 0.0` |

---

## Fallacy Detection — Algorithms Explained

The **Skeptic Agent** (`backend/agents/skeptic.py`) runs two detection passes in sequence:

1. **Structural detection** — pure graph analysis, no API needed (`backend/graph/algorithms.py`)
2. **LLM detection** — Claude classifies semantic fallacies from claim text + graph context

---

### What Is a Strawman?

A **strawman fallacy** occurs when Speaker B attacks a distorted or exaggerated version of Speaker A's argument, rather than what Speaker A actually said.

#### How It's Detected (Structural)

```
For every edge in the graph where relation_type == "attack":
  1. Get the speaker of the attacking claim (src) and the attacked claim (tgt)
  2. If src.speaker != tgt.speaker → Flag as a strawman CANDIDATE
```

**Severity:** `0.5` (structural candidate)

---

### What Is Circular Reasoning?

**Circular reasoning** occurs when a claim is used — directly or through a chain — to support itself.

#### How It's Detected (`detect_cycles()`)

```
python
cycles = list(nx.simple_cycles(graph))
```

**Severity:** `0.7`

---

### What Is Goal-Post Moving?

**Goal-post moving** occurs when a speaker shifts their position after being challenged, without acknowledging that their original claim was weakened.

**Severity:** `0.6`

---

### LLM-Based Fallacy Detection

For fallacies requiring semantic understanding, the Skeptic Agent sends claim batches to Claude with a structured prompt.

**Claude output per fallacy:**

| Field | Type | Description |
|-------|------|-------------|
| `claim_id` | `str` | Which claim contains the fallacy |
| `fallacy_type` | `enum` | One of the 12 supported types |
| `severity` | `float` | 0.0–1.0 |
| `explanation` | `str` | Why this is a fallacy, specifically |
| `socratic_question` | `str` | A question to prompt critical thinking |

---

## Fallacy Types Detected

| Fallacy | Detection Method |
|---------|-----------------|
| Strawman | Structural (cross-speaker attack edges) + LLM semantic check |
| Circular Reasoning | Structural (DFS cycle detection via `nx.simple_cycles`) |
| Goal-Post Moving | Structural (attack + no concession + later claims) |
| Ad Hominem | Rule-based (keyword patterns) + LLM |
| False Dilemma | Rule-based + LLM |
| Slippery Slope | Rule-based + LLM |
| Appeal to Emotion | LLM only |
| Red Herring | LLM only |
| Appeal to Authority | Rule-based + LLM |
| Hasty Generalization | LLM only |
| Tu Quoque | LLM only |
| Equivocation | LLM only |

---

## Database & Observability

### Schema

| Table | Key Columns | What It Stores |
|-------|-------------|----------------|
| `jobs` | `job_id`, `status`, `audio_filename`, `duration_s` | One row per analysis run |
| `claims` | `job_id`, `claim_id`, `speaker`, `text`, `claim_type` | Extracted claims |
| `relations` | `source_claim_id`, `target_claim_id`, `relation_type` | Graph edges |
| `fallacies` | `claim_id`, `fallacy_type`, `severity`, `explanation` | Detected fallacies |
| `fact_checks` | `claim_id`, `verdict`, `confidence`, `explanation` | Fact-check verdicts |
| `llm_calls` | `job_id`, `agent_name`, `system_prompt`, `response_text` | Full LLM audit trail |
| `rigor_scores` | `speaker`, `overall_score`, `supported_ratio` | Per-speaker rigor metrics |

---

## Configuration

All settings are in `backend/config/settings.py` and can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `claude-haiku-4-5` | Primary LLM for analysis |
| `LLM_TEMPERATURE` | `0.1` | Temperature (lower = more deterministic) |
| `TAVILY_SEARCH_DEPTH` | `advanced` | Tavily search depth |
| `TAVILY_MAX_RESULTS` | `5` | Max sources per fact-check |

---

## Logging

Logs are stored at **project root** in the `logs/` directory (override with env `LOG_DIR`). One folder per session, named by **timestamp**: `logs/session_<YYYYmmdd_HHMMSS_ffffff>/` (e.g. `session_20260224_143022_123456`). Text logs plus **structured JSONL** for full traceability.

| File | Content |
|------|--------|
| `meta.json` | Session start/end times (UTC). |
| `README.txt` | Short description of each file. |
| `llm_calls.jsonl` | Every LLM call: provider, model, role, **input** (system + user), **output**, usage, duration, timestamp. |
| `nodes.jsonl` | Every graph node (claim) created: node_id, claim payload, source, timestamp. |
| `edges.jsonl` | Every edge (relation) created: source_id, target_id, relation_type, confidence, source, timestamp. |
| `fallacies.jsonl` | Every fallacy annotation + source (skeptic_structural / skeptic_llm / skeptic_rule_based). |
| `factchecks.jsonl` | Every fact-check result + timestamp. |
| `transcription_chunks.jsonl` | STT chunk outputs: chunk_index, time_offset, segments, duration. |
| `pipeline.txt` | Main pipeline flow (text). |
| `streaming.txt` | Live streaming pipeline (text). |
| `transcription.txt` | STT/diarization details. |
| `ontological.txt` / `skeptic.txt` / `researcher.txt` | Per-agent text logs. |
| `errors.txt` | All ERROR-level logs. |

Each `.jsonl` line is one JSON object. Timestamps are ISO 8601 UTC.

---

## Real-time transcription (streaming)

For **incremental graph building** and true real-time diarization, OpenAI’s **Realtime API** is the right path: transcription-only sessions over WebSocket, with `conversation.item.input_audio_transcription.delta` / `.completed` events. It supports `gpt-4o-transcribe` and `gpt-4o-transcribe-diarize`. The current **file upload** flow uses chunked batch transcription (2‑min chunks) to avoid 500 errors on long files; the **live streaming** pipeline already processes audio chunk-by-chunk. To get real-time diarization end-to-end, the next step is to plug the Realtime API (WebSocket) into the streaming pipeline instead of one-shot `audio.transcriptions.create` per chunk. See [Realtime transcription](https://platform.openai.com/docs/guides/realtime-transcription).

---

## Future Extensions

- **Formal Logic Reconstruction** — Transform arguments into propositional/first-order logic
- **AI Content Detection** — Detect AI-generated speech in online debates
- **Multilingual Support** — Pipeline is language-agnostic with appropriate STT/LLM
- **Public API** — Send audio, receive structured graph + annotations
- **Gamification** — Educational mode where users identify fallacies before the system
- **Key Point Analysis** — Summarize debates into weighted key points (IBM Project Debater-inspired)

---

## License

MIT

---

*DebateGraph v0.2 — Design Document by Alexandre, February 2026*
