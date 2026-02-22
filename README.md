# DebateGraph

**Real-Time Argumentative Analysis Engine — From Speech to Structured Logic**

DebateGraph transforms audio/video debates into interactive argument graphs. It combines speech-to-text with speaker diarization, LLM-powered claim extraction, automated fallacy detection, asynchronous fact-checking, and dynamic graph visualization.

> **Epistemic co-pilot**: the system structures, verifies, and questions arguments — while leaving interpretation to the user.

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

**Why Docker?**
- **Reproducible environment**: eliminates "works on my machine" issues — Python version, system dependencies (ffmpeg), and Node.js are all pinned inside the images.
- **One-command deployment**: `docker-compose up -d` starts the entire stack (backend + frontend + Redis) with proper networking, volume mounts for logs/uploads, and environment variable injection from `.env`.
- **Isolation**: each service runs in its own container with its own dependencies. The backend's heavy Python ML/API dependencies don't interfere with the frontend's Node.js toolchain.
- **Production-ready**: the compose file includes `restart: unless-stopped`, shared volumes for persistent logs and uploads, and inter-service networking (the frontend proxies API calls to the backend container).

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

### Example

```
[Obama] "We've created 5 million jobs" (c1, premise, factual)
    │
    │ support
    ▼
[Obama] "The economy is recovering" (c2, conclusion)
    ▲
    │ attack
    │
[Romney] "The unemployment rate is still too high" (c3, rebuttal, factual)
```

Here, `c1 → c2` (support: evidence for conclusion) and `c3 → c2` (attack: challenges the conclusion). Both edges point **toward** the conclusion being argued about, regardless of when each claim was spoken.

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
| **Deployment** | Docker, Docker Compose, Vercel-compatible frontend |

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **ffmpeg** (for audio conversion)
- API keys (optional — demo mode works without them)

### 1. Clone & Configure

```bash
git clone https://github.com/your-username/DebateGraph.git
cd DebateGraph
cp .env.example .env
# Edit .env with your API keys (optional)
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install fastapi uvicorn python-dotenv pydantic networkx anthropic aiofiles python-multipart openai
# Optional for fact-checking:
# pip install tavily-python

python main.py
```

Backend runs at **http://localhost:8000**

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:5173** (proxies `/api` to backend)

### 4. Try It

1. Open **http://localhost:5173**
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

## Deployment

### Docker Compose (VPS)

```bash
cp .env.example .env
# Edit .env with your API keys
docker-compose up -d
```

Services:
- **Backend**: http://localhost:8000
- **Frontend**: http://localhost:3000
- **Redis**: localhost:6379

### Vercel (Frontend Only)

The frontend can be deployed to Vercel with the backend hosted separately:

1. Set `VITE_API_URL` environment variable to your backend URL
2. Deploy the `frontend/` directory as a Vite project
3. Configure rewrites in `vercel.json` if needed

### Manual VPS

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend (build + serve)
cd frontend
npm run build
npx serve -s dist -l 3000
```

---

## Fallacy Types Detected

| Fallacy | Detection Method |
|---------|-----------------|
| Strawman | Structural (attack edges + speaker mismatch) + LLM |
| Circular Reasoning | Structural (DFS cycle detection in NetworkX) |
| Goal-Post Moving | Structural (claim evolution after refutation) |
| Ad Hominem | Rule-based (keyword patterns) + LLM |
| False Dilemma | Rule-based + LLM |
| Slippery Slope | Rule-based + LLM |
| Appeal to Emotion | LLM |
| Red Herring | LLM |
| Appeal to Authority | Rule-based + LLM |
| Hasty Generalization | LLM |
| Tu Quoque | LLM |
| Equivocation | LLM |

---

## Fact-Checking Pipeline — How It Works

The Researcher Agent fact-checks every claim marked `is_factual=true` by the Ontological Agent. Each fact-check involves **two API calls** in sequence:

### Step 1: Tavily Web Search

| | Details |
|---|--------|
| **API** | [Tavily Search API](https://tavily.com/) |
| **Input** | The claim text, prefixed with `"fact check: "`. Example: `"fact check: We've gone from $10 trillion of national debt to $16 trillion of national debt."` |
| **Parameters** | `search_depth="advanced"`, `max_results=5` |
| **Output** | A list of up to 5 web sources, each containing: URL, page title, content snippet (~200 words), and a Tavily AI-generated summary of all results combined |

Example Tavily output for the claim above:
```
[Source 1] Ryan's Budget Spin - FactCheck.org
  URL: https://www.factcheck.org/2011/05/ryans-budget-spin/
  Content: "...the public debt would increase from $10 trillion in 2011 to $16 trillion in 2021..."

[Source 2] History of the Debt - TreasuryDirect
  URL: https://treasurydirect.gov/government/historical-debt-outstanding/
  Content: "...Between 1980 and 1990, the debt..."

Tavily AI Summary: "The U.S. national debt increased from $10 trillion to $16 trillion.
The rise was due to budget deficits and increased spending..."
```

### Step 2: Claude Verdict Synthesis

| | Details |
|---|--------|
| **API** | Anthropic Claude Haiku (`claude-3-haiku-20240307`) |
| **Input** | A structured prompt containing: (1) the original claim text, (2) the speaker ID, (3) all Tavily search results with URLs and content snippets |
| **System prompt** | `"You are a fact-checking research assistant. Given a factual claim and web search results, determine whether the claim is supported, refuted, partially true, or unverifiable."` |
| **Output** | A JSON object with: `verdict` (enum), `confidence` (0.0–1.0), `explanation` (detailed text with source references), `key_finding` (one-sentence summary) |

Example Claude output:
```json
{
  "verdict": "supported",
  "confidence": 0.9,
  "explanation": "Source 1 (FactCheck.org) confirms the public debt rose from $10T to $16T. Source 2 (TreasuryDirect) provides official historical data consistent with this claim.",
  "key_finding": "The national debt figures cited are accurate based on Treasury data."
}
```

### Verdict Types

| Verdict | Meaning |
|---------|---------|
| `supported` | The claim is substantially accurate based on reliable sources |
| `refuted` | The claim is clearly false or significantly misleading |
| `partially_true` | The claim contains some truth but is incomplete, exaggerated, or missing context |
| `unverifiable` | Insufficient evidence found to determine truth value |
| `pending` | Not yet checked (initial state) |

### Error Handling

If Claude returns malformed JSON (observed in ~1.4% of calls), the system falls back to `verdict: "unverifiable"` with `confidence: 0.0`. No claim is left unchecked.

---

## Fallacy Detection — Algorithms Explained

The Skeptic Agent uses **three detection methods** in sequence: structural graph analysis, rule-based keyword matching, and LLM-based classification.

### Strawman Detection

A **strawman fallacy** occurs when Speaker A misrepresents Speaker B's argument, then attacks the distorted version instead of the real one.

**How it's detected (structural method):**

1. Find all **attack edges** in the graph (edges where `relation_type = "attack"`)
2. For each attack edge `(attacker_claim → target_claim)`, check if the speakers are different
3. If different speakers: compute **cosine similarity** between the attacker's claim text and the target's claim text using word-overlap (bag-of-words)
4. If similarity is **below the threshold** (default: 0.75), the attack is flagged as a potential strawman — the attacker is attacking something that doesn't closely match what the target actually said

```
Example:
  [Romney] "I will create 12 million jobs" (c1)
  [Obama]  "Romney wants to fire teachers and police" (c2) --attack--> c1

  Cosine similarity between c1 and c2 = 0.15 (very low)
  → Flagged as STRAWMAN: Obama is attacking a distorted version of Romney's claim
```

The LLM also independently checks for strawman patterns, catching cases where the distortion is semantic rather than lexical.

### Circular Reasoning (Cycle Detection)

**Circular reasoning** occurs when a claim is used to support itself, directly or through a chain of intermediate claims.

**How it's detected:**

1. Run **depth-first search (DFS)** on the NetworkX directed graph, following only `support` and `implication` edges
2. If DFS finds a **back edge** (an edge pointing to an ancestor in the DFS tree), a cycle exists
3. Extract the full cycle path (e.g., `c1 → c3 → c7 → c1`)
4. Flag all claims in the cycle with `fallacy_type: "circular_reasoning"`

```
Example:
  c1: "We need more regulation" --support--> c2: "The market is failing"
  c2: "The market is failing" --support--> c3: "Companies are irresponsible"
  c3: "Companies are irresponsible" --support--> c1: "We need more regulation"

  DFS detects cycle: c1 → c2 → c3 → c1
  → All three claims flagged as CIRCULAR REASONING
```

In practice, cycles are rare in well-structured debates (0 cycles detected in the Obama/Romney test). When they occur, they indicate a genuine logical flaw.

### Goal-Post Moving Detection

**Goal-post moving** occurs when a speaker changes their success criteria or position after being challenged.

**How it's detected:**

1. Find all claims by the same speaker that are **targets of attack edges** from the opponent
2. Look for subsequent claims by the same speaker that **modify or narrow** the original claim
3. If a speaker's claim is attacked, and they later make a related but shifted claim (detected by partial text overlap + timestamp ordering), flag as goal-post moving

```
Example:
  [Romney] "I will balance the budget" (c1, t=180s)
  [Obama]  "The math doesn't add up" (c2, t=190s) --attack--> c1
  [Romney] "I will balance the budget over 8-10 years" (c3, t=210s)

  c3 is a narrowed version of c1, made after c1 was attacked
  → Flagged as GOAL-POST MOVING
```

### Topic Drift Detection

**Topic drift** measures how much the debate wanders from its original topics.

**How it's detected:**

1. Sort all claims chronologically by `timestamp_start`
2. Compute text similarity between consecutive claims using word overlap
3. When similarity drops below a threshold between consecutive claims, mark a **drift point**
4. Count total drift points — higher count means more topic changes

### LLM-Based Fallacy Detection

For fallacies that require semantic understanding (ad hominem, appeal to emotion, hasty generalization, etc.), the system sends claim batches to Claude Haiku with a specialized prompt. The LLM returns structured JSON identifying:

- Which claim contains the fallacy
- The fallacy type (from a predefined list of 12 types)
- Severity score (0.0–1.0)
- A human-readable explanation
- A Socratic question to help the listener think critically

---

## Database & Observability — Design Goals

### What Should Be Stored in the Database

Every input and output from every agent should be persisted for full traceability:

| Table | Contents | Purpose |
|-------|----------|---------|
| `jobs` | Job ID, status, audio filename, duration, timestamps | Track analysis runs |
| `transcription_segments` | Speaker, text, start/end timestamps, language | Raw STT output |
| `claims` | ID, speaker, text, claim_type, is_factual, confidence, timestamps | Ontological Agent output |
| `relations` | Source claim ID, target claim ID, relation_type, confidence | Graph edges |
| `fallacies` | Claim ID, fallacy_type, severity, explanation, socratic_question, related_claims | Skeptic Agent output |
| `fact_checks` | Claim ID, verdict, confidence, explanation, sources (JSON array) | Researcher Agent output |
| `tavily_searches` | Claim ID, search query, raw results (JSONB), timestamp | Tavily API raw I/O |
| `llm_calls` | Agent name, model, prompt (text), response (text), tokens used, latency_ms | Full LLM audit trail |
| `rigor_scores` | Speaker, overall_score, supported_ratio, fallacy_count, factcheck_rate, consistency | Per-speaker metrics |
| `graph_snapshots` | Job ID, full snapshot (JSONB), created_at | Complete graph state for frontend |

### Why This Matters

- **Debugging**: if a claim is miscategorized, you can trace back to the exact LLM prompt and response that produced it
- **Auditing**: every fact-check verdict can be verified against the raw Tavily search results
- **Reproducibility**: re-running the same audio should produce comparable results; the DB lets you compare runs
- **Cost tracking**: `llm_calls` table tracks token usage per agent, enabling cost analysis

### Frontend Visualization of DB Data

All information stored in the database should be accessible from the frontend:

| Data | Where to Display | How |
|------|-----------------|-----|
| **Claims + types** | Graph nodes | Color-coded by claim_type (premise=blue, conclusion=green, rebuttal=red, concession=yellow) |
| **Relations + types** | Graph edges | Different line styles (solid=support, dashed=attack, dotted=implication) |
| **Fallacies** | Fallacy Panel (sidebar) + node highlights | Red glow on affected nodes; click to see explanation + socratic question |
| **Fact-check verdicts** | Badge on each node + Fact-Check Panel | Green ✓ (supported), Red ✗ (refuted), Yellow ~ (partial), Gray ? (unverifiable) |
| **Fact-check sources** | Node detail overlay (click a node) | List of URLs with snippets from Tavily |
| **Rigor scores** | Rigor Score panel (per speaker) | Bar chart or radar chart showing each component |
| **Transcription** | Waveform view (bottom panel) | Synchronized transcript with speaker colors, click to jump to audio position |
| **LLM reasoning** | Node detail overlay → "AI Reasoning" tab | Show the exact LLM prompt and response that produced each claim/fallacy/verdict |
| **Raw Tavily results** | Node detail overlay → "Sources" tab | Full search results with URLs, snippets, and AI summary |
| **Job history** | Job list page | Browse past analyses, click to load any previous graph |

The key principle: **every piece of data the pipeline produces should be one click away from the graph view.** Click a node → see its claim, type, fact-check verdict, sources, fallacies, and the LLM reasoning behind each annotation.

---

## Configuration

All settings are in `backend/config/settings.py` and can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `claude-3-haiku-20240307` | Primary LLM for analysis |
| `STT_MODEL` | `gpt-4o-transcribe-diarize` | Speech-to-text model |
| `CHUNK_SIZE` | `10` | Segments per LLM batch |
| `MAX_CONCURRENT_LLM_CALLS` | `3` | Parallel LLM requests |
| `STRAWMAN_SIMILARITY_THRESHOLD` | `0.75` | Cosine similarity for strawman |
| `TAVILY_SEARCH_DEPTH` | `advanced` | Tavily search depth |
| `WHISPER_MODEL` | `medium` | Local Whisper fallback model |

---

## Logging

Each analysis session creates structured logs in `logs/session_<timestamp>/`:

```
logs/session_20260215_143022/
├── pipeline.txt       # Main pipeline flow
├── transcription.txt  # STT details
├── ontological.txt    # Claim extraction details
├── skeptic.txt        # Fallacy detection details
├── researcher.txt     # Fact-checking details
└── errors.txt         # All errors
```

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
