# DebateGraph

**Real-time argumentative analysis** — turn debates (audio/video) into an interactive argument graph with claim extraction, fallacy detection, and fact-checking.

The system structures and verifies arguments while leaving interpretation to the user.

This is an initial prototype. Many changes need to be made: diarization streaming, prompt engineering and context management for better argument classification... 

---

## Installation

**Prerequisites:** Python 3.x, Node.js, ffmpeg (for audio/video). Copy `.env.example` to `.env` and set API keys if you use real transcription/fact-checking.

### Backend

```bash
cd backend
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload
```

Backend runs at **http://localhost:8010**.

### Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:5173**.

---

## How It Works

### Overview

1. You upload an audio/video file.
2. The backend **transcribes** the file (OpenAI `gpt-4o-transcribe-diarize`) with speaker diarization.
3. An **analysis pipeline** runs: extract claims → build argument graph → detect fallacies → fact-check factual claims → compute rigor scores.
4. The frontend **polls** job status and shows progress (transcribing → extracting → complete). When complete, it displays the graph, fallacies, fact-checks, and rigor scores.

So “real-time” here means: **live progress during analysis**, and (in live mic/video stream mode) **incremental graph updates** as chunks are processed. The core value is **claim verification and fallacy detection** applied to the full debate once (or incrementally in stream mode).

### Pipeline (backend)

| Step | What happens |
|------|----------------|
| **1. Transcription** | Audio is converted to WAV; OpenAI returns segments with speaker labels and timestamps. Long files are chunked to avoid API limits. |
| **2. Ontological Agent** | Claude extracts **atomic claims** from the transcript: type (premise, conclusion, rebuttal, concession), relations (support, attack, undercut, reformulation, implication), and flags **factual** vs opinion claims. The result is a **directed graph** (NetworkX): nodes = claims, edges = relations. |
| **3. Skeptic Agent** | **Fallacy detection** in two layers: **(a)** **Structural** (no LLM): cycles (circular reasoning), cross-speaker attack edges (strawman candidates), goal-post moving (attacked claim, no concession, then new claims). **(b)** **LLM**: Claude classifies semantic fallacies (ad hominem, false dilemma, slippery slope, appeal to emotion, red herring, etc.) from claim text and graph context. Each fallacy gets severity, explanation, and a Socratic question. |
| **4. Researcher Agent** | Every claim marked **factual** is **fact-checked**: Tavily web search → Claude synthesizes a verdict from results. Verdicts: `supported`, `refuted`, `partially_true`, `unverifiable`. Without Tavily/Claude keys, mock “unverifiable” results are returned. |
| **5. Rigor scores** | Per-speaker composite score from: share of supported claims, fallacy penalty, fact-check positive rate, internal consistency (self-contradictions), and direct response rate to the other side. |

### What you see in the UI

- **Argument graph**: Nodes = claims (color by speaker). Edges = support (green), attack (red), undercut (violet), reformulation (grey), implication (blue). Click a node for full text and annotations.
- **Fact-check badges** on nodes: supported / refuted / partially true / unverifiable (or pending).
- **Fallacy panel**: List of detected fallacies with type, severity, explanation, and Socratic question.
- **Rigor scores**: Per-speaker breakdown.
- **Waveform + transcript**: For file-based runs, audio playback with transcript and optional sync to graph selection.
- **Progress**: While the job runs, status is shown (e.g. “Transcribing…”, “Extracting claims & detecting fallacies…”).

### Modes

- **Upload**: Upload a file → backend creates a job, runs the pipeline in the background, saves the snapshot to PostgreSQL. Frontend polls `GET /api/status/{job_id}` until complete, then shows the graph.
- **Live stream** (optional): Microphone or audio/video stream sends chunks over WebSocket; backend processes them and pushes updates so the graph grows in real time.

### Fallacies detected

- **Structural**: circular reasoning (cycles), strawman (cross-speaker attack), goal-post moving.
- **LLM / rule-based**: ad hominem, false dilemma, slippery slope, appeal to emotion, red herring, appeal to authority, hasty generalization, tu quoque, equivocation.

### API keys (optional)

| Key | Purpose |
|-----|---------|
| `OPENAI_API_KEY` | Transcription + diarization | 
| `ANTHROPIC_API_KEY` | Claim extraction, fallacy detection, fact-check synthesis |
| `TAVILY_API_KEY` | Web search for fact-checking |
| `DATABASE_URL` | PostgreSQL for jobs and snapshots (optional; without it, jobs are not persisted) |

Without keys, rule-based fallbacks still work; transcription and full fact-check require the keys above.

---

## Project structure

```
backend/
  main.py              # FastAPI app, /api/health
  api/routes/          # upload, status, jobs, snapshot, ws, dbviewer
  agents/              # ontological, skeptic, researcher
  graph/               # store (NetworkX), algorithms (cycles, strawman, goal-post)
  pipeline/            # transcription (OpenAI)
  db/                   # PostgreSQL jobs + graph_snapshots
frontend/
  src/
    App.tsx             # Modes: idle, upload, live, video, audio-stream, video-review
    api.ts              # upload, getJobStatus, loadSnapshot
    components/         # GraphView, WaveformView, FallacyPanel, RigorScore, UploadPanel, …
```

---

## License

MIT
