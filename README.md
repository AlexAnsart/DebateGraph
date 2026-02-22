# DebateGraph

*Real-Time Argumentative Analysis Engine - From Speech to Structured Logic*

DebateGraph transforms debate audio into interactive argument graphs. Using Claude AI, it extracts claims, detects fallacies, fact-checks statements, and visualizes the logical structure of any discussion.

## Features

- **Audio Analysis**: Upload audio/video files or use the built-in demo
- **Claim Extraction**: AI-powered argument parsing with Claude Haiku
- **Fallacy Detection**: Structural + LLM-based fallacy identification (strawman, ad hominem, false dilemma, etc.)
- **Fact-Checking**: Real-time verification via Tavily AI search API
- **Interactive Graph**: Cytoscape.js visualization with speaker color-coding
- **Audio Sync**: WaveSurfer.js waveform with transcript alignment
- **Rigor Scores**: Speaker credibility metrics based on evidence and logic

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- API Keys: Anthropic Claude (required), Tavily (optional for fact-checking)

### Installation

`ash
git clone <repository-url>
cd DebateGraph
cp .env.example .env
# Edit .env with your API keys
`

Backend:

`ash
cd backend
pip install -r requirements-dev.txt
`

Frontend:

`ash
cd frontend
npm install
`

### Running Locally

Terminal 1 (Backend):

`ash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
`

Terminal 2 (Frontend):

`ash
cd frontend
npm run dev
`

Open http://localhost:5173

### Demo Mode

Click **Run Demo** in the UI to analyze a pre-loaded debate transcript. The system extracts ~22 claims, builds an argument graph with ~18 relations, detects ~18 fallacies, fact-checks ~6 statements via Tavily, and generates rigor scores - all in ~40 seconds.

## Architecture

`
Audio -> Transcription (WhisperX) -> Diarization (pyannote)
  -> Ontological Agent (Claude Haiku) -> Claim Extraction + Relations
  -> Skeptic Agent (Structural + LLM) -> Fallacy Detection
  -> Researcher Agent (Tavily + Claude) -> Fact-Checking
  -> Graph Construction (NetworkX) -> Rigor Scores -> Frontend
`

### Backend (FastAPI + Python)

`
backend/
  api/models/schemas.py        Pydantic models
  api/routes/upload.py         File upload and analysis
  api/routes/ws.py             WebSocket handlers
  agents/ontological.py        Claim extraction (Claude)
  agents/skeptic.py            Fallacy detection
  agents/researcher.py         Fact-checking (Tavily + Claude)
  agents/orchestrator.py       Pipeline coordinator
  pipeline/transcription.py    WhisperX integration
  pipeline/diarization.py      Speaker separation
  graph/store.py               NetworkX graph store
  graph/algorithms.py          Graph analysis
  config/settings.py           LLM prompts and thresholds
  config/logging_config.py     Session logging
  utils/audio.py               Audio utilities
  main.py                      FastAPI entrypoint
`

### Frontend (React + TypeScript)

`
frontend/src/
  components/GraphView.tsx     Cytoscape visualization
  components/WaveformView.tsx  Audio player + transcript
  components/FallacyPanel.tsx  Fallacy list with socratic questions
  components/NodeDetail.tsx    Claim detail overlay
  components/RigorScore.tsx    Speaker metrics
  components/UploadPanel.tsx   Drag-and-drop upload
  components/FactCheckBadge.tsx  Verdict badges
  hooks/useWebSocket.ts        Real-time updates
  hooks/useAudioCapture.ts     Mic input (Phase 2)
  types.ts                     TypeScript definitions
  api.ts                       API client
`

## Configuration

### Environment Variables (.env)

`
ANTHROPIC_API_KEY=sk-ant-api03-...     # Required
TAVILY_API_KEY=tvly-...                # Optional (fact-checking)
HUGGINGFACE_TOKEN=hf_...              # Optional (diarization)
WHISPER_MODEL=medium                   # tiny|base|small|medium|large-v3
WHISPER_DEVICE=auto                    # cuda|cpu|auto
STRAWMAN_SIMILARITY_THRESHOLD=0.75
`

### LLM Prompts

All prompts configurable in backend/config/settings.py:
- ONTOLOGICAL_SYSTEM_PROMPT: Claim extraction instructions
- SKEPTIC_SYSTEM_PROMPT: Fallacy detection logic
- RESEARCHER_SYSTEM_PROMPT: Fact-checking methodology

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/health | Service health check |
| POST | /api/upload | Upload audio file for analysis |
| GET | /api/status/{job_id} | Get analysis status |
| POST | /api/demo | Run demo analysis |
| GET | /api/jobs | List all jobs |
| DELETE | /api/jobs/{job_id} | Delete job |
| WS | /ws/{job_id} | Real-time analysis updates |

## Docker Deployment

`ash
docker-compose up --build
`

Or individually:

`ash
docker build -t debategraph-backend ./backend
docker run -p 8001:8001 -e ANTHROPIC_API_KEY=... debategraph-backend

docker build -t debategraph-frontend ./frontend
docker run -p 80:80 debategraph-frontend
`

## Tech Stack

- Backend: FastAPI, Claude Haiku, WhisperX, Tavily, NetworkX, Pydantic
- Frontend: React 18, TypeScript, Vite 7, Tailwind CSS 4, Cytoscape.js, WaveSurfer.js
- Infrastructure: Docker, Docker Compose, Redis

## Performance (Demo)

- Time: ~40 seconds
- Claims: 22 extracted
- Relations: 18 argumentative links
- Fallacies: 18 detected
- Fact-checks: 6 completed
- Rigor Scores: 2 speakers evaluated

## Roadmap

- Phase 2: WebSocket streaming, live audio capture, incremental graph updates
- Phase 3: Multi-language support, emotion analysis, debate summarization
- Phase 4: Public API, gamification, formal logic verification
