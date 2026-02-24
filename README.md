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

## Fact-Checking Pipeline — Complete I/O Reference

The **Researcher Agent** (`backend/agents/researcher.py`) fact-checks every claim where `is_factual=True`. The `is_factual` flag is set by the Ontological Agent: a claim is considered factual if it contains verifiable statistics, dates, named studies, or specific numerical data (e.g. percentages, dollar amounts, counts).

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

```python
{
  "results": [
    {
      "title": "Ryan's Budget Spin - FactCheck.org",
      "url": "https://www.factcheck.org/2011/05/ryans-budget-spin/",
      "content": "...the public debt would increase from $10 trillion in 2011 to $16 trillion...",
      # content is truncated to ~300 chars before being passed to Claude
    },
    # up to 4 more sources
  ],
  "answer": "The U.S. national debt increased from $10 trillion to $16 trillion. The rise was due to budget deficits..."
  # Tavily's own AI-generated summary across all results
}
```

The agent extracts:
- **`sources`** — list of up to 5 URLs (stored in `FactCheckResult.sources`)
- **`search_results_text`** — formatted string combining all source titles, URLs, content snippets, and the Tavily AI summary; passed as-is to Claude

---

### Step 2 — Claude Verdict Synthesis

**File:** `backend/agents/researcher.py` → `_synthesize_verdict()`  
**Model:** `claude-3-haiku-20240307` (configured via `LLM_MODEL` in `settings.py`)  
**Config:** `LLM_MAX_TOKENS_FACTCHECK` (default: `1500`), `LLM_TEMPERATURE` (default: `0.1`)

#### System Prompt (exact, from `settings.py`)

```
You are a fact-checking research assistant. Given a factual claim and web search results,
determine whether the claim is supported, refuted, partially true, or unverifiable.

Be precise and cite specific sources. Distinguish between exact claims and approximate ones.
```

#### User Prompt Template (exact, from `settings.py`)

```
Based on these search results, evaluate this factual claim:

CLAIM: "{claim_text}"
SPEAKER: {speaker}

SEARCH RESULTS:
{search_results}   ← the formatted Tavily output from Step 1

Respond with ONLY valid JSON:
{
  "verdict": "supported|refuted|partially_true|unverifiable",
  "confidence": 0.8,
  "explanation": "Detailed explanation with specific references to sources",
  "key_finding": "One-sentence summary of the verdict"
}
```

#### Output (Claude JSON response)

```json
{
  "verdict": "supported",
  "confidence": 0.9,
  "explanation": "Source 1 (FactCheck.org) confirms the public debt rose from $10T to $16T between 2009 and 2012. Source 2 (TreasuryDirect) provides official historical data consistent with this claim.",
  "key_finding": "The national debt figures cited are accurate based on Treasury data."
}
```

This is parsed into a `FactCheckResult` Pydantic object and stored in the graph.

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
| No `TAVILY_API_KEY` | Returns `verdict: "unverifiable"`, `confidence: 0.3`, with a message explaining no API is configured |
| Tavily succeeds but no `ANTHROPIC_API_KEY` | Uses keyword matching on Tavily's `answer` field to infer verdict (words like "true"/"confirmed" → `supported`; "false"/"debunked" → `refuted`) |
| Claude returns malformed JSON | Falls back to `verdict: "unverifiable"`, `confidence: 0.0` — no claim is left without a result |
| Any exception during Tavily call | Returns `verdict: "unverifiable"` with the error message in `explanation` |

---

### What Gets Stored Per Fact-Check

Every fact-check produces a `FactCheckResult` with:

| Field | Type | Description |
|-------|------|-------------|
| `claim_id` | `str` | Links back to the claim node in the graph |
| `verdict` | `enum` | `supported / refuted / partially_true / unverifiable / pending` |
| `confidence` | `float` | 0.0–1.0, Claude's self-reported confidence |
| `explanation` | `str` | Full Claude explanation with source references |
| `sources` | `list[str]` | Up to 5 URLs from Tavily |

For full auditability, the raw Tavily search results (query, all source snippets, AI summary) and the exact Claude prompt + response should be persisted in the `tavily_searches` and `llm_calls` DB tables (see Database section below).

---

## Fallacy Detection — Algorithms Explained

The **Skeptic Agent** (`backend/agents/skeptic.py`) runs two detection passes in sequence:

1. **Structural detection** — pure graph analysis, no API needed (`backend/graph/algorithms.py`)
2. **LLM detection** — Claude classifies semantic fallacies from claim text + graph context

---

### What Is a Strawman?

A **strawman fallacy** occurs when Speaker B attacks a distorted or exaggerated version of Speaker A's argument, rather than what Speaker A actually said. The name comes from the idea of building a "straw man" (a weak, fake version of the opponent's position) that is easy to knock down.

**Example:**
> Speaker A: "We should reduce military spending by 10% to fund education."  
> Speaker B: "My opponent wants to leave our country completely defenseless!"

Speaker B is not attacking what A said — they've replaced A's specific, limited proposal with an extreme caricature.

#### How It's Detected (Structural — `detect_strawman_candidates()`)

**File:** `backend/graph/algorithms.py`

```
For every edge in the graph where relation_type == "attack":
  1. Get the speaker of the attacking claim (src) and the attacked claim (tgt)
  2. If src.speaker == tgt.speaker → skip (can't strawman yourself)
  3. If src.speaker != tgt.speaker → this is a cross-speaker attack
     → Flag as a strawman CANDIDATE
     → Record: attacking_claim_id, original_claim_id, attacker, original_speaker,
               attacking_text, original_text
```

The structural pass identifies **all cross-speaker attack edges** as candidates. It does not yet compute text similarity — that semantic check is done by the Skeptic Agent using the candidate list.

The **LLM pass** then independently checks for strawman patterns in the claim text, catching cases where the distortion is semantic (paraphrase, implication) rather than lexical.

**Severity:** `0.5` (structural candidate) — raised by LLM if confirmed semantically.

---

### What Is Circular Reasoning?

**Circular reasoning** (also called *petitio principii* or "begging the question") occurs when a claim is used — directly or through a chain — to support itself. The argument goes in a circle: the conclusion is assumed in the premises.

**Example:**
> "The Bible is true because it says so in the Bible."

Or in a chain:
> "We need more regulation" → supports → "The market is failing" → supports → "Companies are irresponsible" → supports → "We need more regulation"

#### How It's Detected (`detect_cycles()`)

**File:** `backend/graph/algorithms.py`

```python
cycles = list(nx.simple_cycles(graph))
```

NetworkX's `simple_cycles()` runs a **DFS-based algorithm** (Johnson's algorithm) that finds all elementary cycles in the directed graph. A cycle exists when DFS encounters a **back edge** — an edge pointing to an ancestor already on the current DFS path.

```
For each cycle found (e.g. [c1, c3, c7]):
  → Flag c1 with fallacy_type: "circular_reasoning"
  → severity: 0.7
  → explanation: "Circular reasoning: claims c1 → c3 → c7 form a logical loop."
  → related_claim_ids: [c3, c7]
  → socratic_question: "Can any of these claims stand on its own without relying on the others?"
```

The cycle detection runs on **all edge types** (not just `support`/`implication`), so any directed loop in the graph is flagged. In practice, cycles are rare in well-structured debates — 0 cycles were detected in the Obama/Romney test dataset.

**Complexity:** O(V + E) for the DFS traversal.

---

### What Is Goal-Post Moving?

**Goal-post moving** occurs when a speaker shifts their position or success criteria after being challenged, without acknowledging that their original claim was weakened. Instead of conceding or defending the original point, they quietly substitute a new, narrower, or different claim.

**Example:**
> Speaker A: "My plan will balance the budget." (t=180s)  
> Speaker B: "The math doesn't add up — it creates a $2T deficit." (t=190s) → attacks A's claim  
> Speaker A: "Well, my plan will balance the budget over 8–10 years." (t=210s)

A never conceded the original claim; they just moved the goalposts.

#### How It's Detected (`detect_goalpost_moving()`)

**File:** `backend/graph/algorithms.py`

```
For each speaker, sort their claims by timestamp_start.

For each claim C by speaker S:
  1. Find all incoming attack edges from a DIFFERENT speaker
     (i.e. opponents who attacked C)
  2. If no attackers → skip
  3. Look at all of S's claims that come AFTER C chronologically
  4. Check if any of those later claims have claim_type == "concession"
     → If YES: speaker acknowledged the challenge → not goal-post moving
     → If NO: speaker was attacked, made new claims, but never conceded
        → Flag C as GOAL_POST_MOVING
        → Record: speaker, original_claim_id, attacked_by (list), subsequent_claims (next 3)
```

**Severity:** `0.6`

---

### What Is Topic Drift?

**Topic drift** measures how much the debate wanders away from its original subject matter over time.

#### How It's Detected (`detect_topic_drift()`)

**File:** `backend/graph/algorithms.py`

```
1. Sort all claims chronologically by timestamp_start
2. Define "initial topic" = first window_size (default: 5) claims
3. Slide a window of size 5 across the remaining claims
4. For each window:
   - Count how many claims in the window have a graph path to any initial claim
   - connectivity = connected_count / window_size
   - If connectivity < 0.5 → flag as a drift point
     → Record: timestamp, connectivity_to_original, window_claims (text previews)
```

Topic drift is reported as metadata on the analysis but is not currently flagged as a fallacy — it's a structural observation about the debate's coherence.

---

### LLM-Based Fallacy Detection

For fallacies requiring semantic understanding, the Skeptic Agent sends claim batches to Claude with a structured prompt.

**System prompt (exact, from `settings.py`):**
```
You are an expert in informal logic, critical thinking, and argumentation theory.
Your role is to identify logical fallacies in debate arguments with precision and fairness.
Only flag clear fallacies — not mere rhetorical emphasis or strong language.
A fallacy must involve a genuine logical error, not just a debatable point.
```

**User prompt** includes, for each claim:
```
[c1] SPEAKER_00 (premise, factual): "claim text here" --[attack]--> c3 <--[support]-- c2
```

Each claim is annotated with its ID, speaker, type, factual flag, and all its graph edges (both outgoing and incoming), giving Claude full structural context.

**Claude output per fallacy:**

| Field | Type | Description |
|-------|------|-------------|
| `claim_id` | `str` | Which claim contains the fallacy |
| `fallacy_type` | `enum` | One of the 12 supported types |
| `severity` | `float` | 0.0–1.0 (0.3=minor, 0.5=moderate, 0.7=significant, 0.9=severe) |
| `explanation` | `str` | Why this is a fallacy, specifically |
| `socratic_question` | `str` | A question to prompt critical thinking (non-accusatory) |
| `related_claim_ids` | `list[str]` | Other claims involved in the fallacy |

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

### Design Goal

Every input and output from every agent should be persisted for full traceability. If a claim is miscategorized, you should be able to trace back to the exact LLM prompt and response that produced it. If a fact-check verdict seems wrong, you should be able to inspect the raw Tavily results that Claude was given.

### Schema

| Table | Key Columns | What It Stores |
|-------|-------------|----------------|
| `jobs` | `job_id`, `status`, `audio_filename`, `duration_s`, `created_at`, `completed_at` | One row per analysis run |
| `transcription_segments` | `job_id`, `speaker`, `text`, `start_s`, `end_s`, `language` | Raw STT output — one row per diarized segment |
| `claims` | `job_id`, `claim_id`, `speaker`, `text`, `claim_type`, `is_factual`, `confidence`, `timestamp_start`, `timestamp_end` | Ontological Agent output — one row per extracted claim |
| `relations` | `job_id`, `source_claim_id`, `target_claim_id`, `relation_type`, `confidence` | Graph edges — one row per inferred relation |
| `fallacies` | `job_id`, `claim_id`, `fallacy_type`, `severity`, `explanation`, `socratic_question`, `related_claim_ids` (JSON array), `detection_method` (`structural`/`llm`/`rule`) | Skeptic Agent output |
| `fact_checks` | `job_id`, `claim_id`, `verdict`, `confidence`, `explanation`, `sources` (JSON array) | Researcher Agent output — final verdict per claim |
| `tavily_searches` | `job_id`, `claim_id`, `query`, `raw_results` (JSONB), `tavily_answer`, `searched_at` | **Full Tavily I/O** — the exact query sent and every source returned |
| `llm_calls` | `job_id`, `agent_name`, `model`, `system_prompt`, `user_prompt`, `response_text`, `tokens_input`, `tokens_output`, `latency_ms`, `called_at` | **Full LLM audit trail** — every prompt and response from every agent |
| `rigor_scores` | `job_id`, `speaker`, `overall_score`, `supported_ratio`, `fallacy_count`, `factcheck_rate`, `consistency_score` | Per-speaker rigor metrics |
| `graph_snapshots` | `job_id`, `snapshot` (JSONB), `created_at` | Complete serialized graph state for frontend replay |

### Why Each Table Matters

- **`llm_calls`** — If a claim is miscategorized (e.g. a premise labeled as a conclusion), you can pull the exact prompt the Ontological Agent sent to Claude and the raw JSON response it received. Same for every fallacy annotation and every fact-check verdict.
- **`tavily_searches`** — If a fact-check verdict seems wrong, you can inspect the exact sources Tavily returned and the AI summary Claude was given. The raw JSONB includes all 5 source URLs, titles, and content snippets.
- **`fallacies.detection_method`** — Distinguishes whether a fallacy was found by structural graph analysis, rule-based keyword matching, or LLM classification. Useful for evaluating each method's precision.
- **`rigor_scores`** — Enables longitudinal analysis: compare the same speaker across multiple debates, or track how rigor scores correlate with fact-check outcomes.
- **`graph_snapshots`** — Enables the frontend to replay any past analysis without re-running the pipeline.

---

## Frontend Visualization of DB Data

The key principle: **every piece of data the pipeline produces should be one click away from the graph view.**

### Graph View (Primary)

| Data | Visual Encoding |
|------|----------------|
| Claims | Nodes, color-coded by `claim_type`: premise=blue, conclusion=green, rebuttal=red, concession=yellow |
| Speaker attribution | Node border color or shape per speaker |
| Relations | Directed edges: solid line=support, dashed=attack, dotted=implication, double=undercut |
| Fallacies | Red glow / warning icon on affected nodes |
| Fact-check verdict | Badge on node: ✓ green (supported), ✗ red (refuted), ~ yellow (partially true), ? gray (unverifiable) |
| Rigor scores | Speaker legend with score bar |

### Node Detail Overlay (Click Any Node)

Clicking a node opens a detail panel with **four tabs**:

| Tab | Contents |
|-----|----------|
| **Claim** | Full claim text, speaker, type, timestamp, `is_factual` flag, confidence score |
| **Fact-Check** | Verdict badge, confidence, full Claude explanation, list of source URLs with snippets (from `tavily_searches`) |
| **Fallacies** | All fallacies detected on this claim: type, severity badge, explanation, socratic question, related claim IDs |
| **AI Reasoning** | The exact LLM prompt sent to Claude and the raw response received (from `llm_calls`) — for full transparency |

### Sidebar Panels

| Panel | Contents |
|-------|----------|
| **Fallacy Panel** | Chronological list of all detected fallacies with severity badges; click to highlight the node in the graph |
| **Fact-Check Panel** | All factual claims with their verdicts; click to jump to the node |
| **Rigor Scores** | Per-speaker breakdown: overall score + component bars (supported ratio, fallacy penalty, fact-check rate, consistency) |
| **Transcript** | Synchronized waveform + speaker-colored transcript; click any segment to jump to audio position and highlight the corresponding graph node |

### Job History Page

A dedicated page listing all past analysis runs from the `jobs` table:

| Column | Description |
|--------|-------------|
| Job ID | Unique identifier |
| Audio file | Original filename |
| Duration | Audio length |
| Status | `pending / processing / complete / failed` |
| Claims | Count of extracted claims |
| Fallacies | Count of detected fallacies |
| Fact-checks | Count of verified claims |
| Created at | Timestamp |

Clicking any row loads the corresponding `graph_snapshot` and renders the full graph + all annotations — no re-processing needed.

---

## Configuration

All settings are in `backend/config/settings.py` and can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `claude-3-haiku-20240307` | Primary LLM for analysis |
| `LLM_MODEL_FALLBACK` | `claude-haiku-4-5` | Fallback if primary model fails |
| `LLM_MAX_TOKENS_EXTRACTION` | `4096` | Max tokens for claim extraction |
| `LLM_MAX_TOKENS_FALLACY` | `3000` | Max tokens for fallacy detection |
| `LLM_MAX_TOKENS_FACTCHECK` | `1500` | Max tokens for fact-check verdict |
| `LLM_TEMPERATURE` | `0.1` | Temperature (lower = more deterministic) |
| `STT_MODEL` | `gpt-4o-transcribe-diarize` | Speech-to-text model |
| `CHUNK_SIZE` | `10` | Segments per LLM batch |
| `MAX_CONCURRENT_LLM_CALLS` | `3` | Parallel LLM requests |
| `STRAWMAN_SIMILARITY_THRESHOLD` | `0.75` | Cosine similarity threshold for strawman |
| `TAVILY_SEARCH_DEPTH` | `advanced` | Tavily search depth |
| `TAVILY_MAX_RESULTS` | `5` | Max sources per fact-check |
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
