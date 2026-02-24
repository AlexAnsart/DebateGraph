"""
Structured session logger: one folder per session with organized JSONL files.
Logs every LLM call (input/output), every node/edge created, fallacies, factchecks,
and transcription chunks — all with timestamps.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class SessionLogger:
    """
    Writes structured logs to a session directory. Thread-safe append-only JSONL files.
    One folder per session; multiple files for different event types.
    """

    def __init__(self, session_dir: str):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._call_counter = 0
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._write_meta()

    def _lock(self, name: str) -> threading.Lock:
        if name not in self._locks:
            self._locks[name] = threading.Lock()
        return self._locks[name]

    def _append_jsonl(self, filename: str, obj: dict) -> None:
        path = self.session_dir / filename
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        with self._lock(filename):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)

    def _write_meta(self) -> None:
        meta = {
            "session_dir": str(self.session_dir),
            "started_at_utc": self._started_at,
        }
        path = self.session_dir / "meta.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        readme = self.session_dir / "README.txt"
        readme.write_text(
            "Structured session logs. One JSON object per line in .jsonl files.\n"
            "llm_calls.jsonl = every LLM request/response with input/output and timestamps.\n"
            "nodes.jsonl = every graph node (claim) created.\n"
            "edges.jsonl = every graph edge (relation) created.\n"
            "fallacies.jsonl = every fallacy annotation.\n"
            "factchecks.jsonl = every fact-check result.\n"
            "transcription_chunks.jsonl = STT chunk outputs.\n",
            encoding="utf-8",
        )

    def set_ended_at(self) -> None:
        """Call when session ends to record end time in meta."""
        path = self.session_dir / "meta.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            meta = {}
        meta["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def log_llm_call(
        self,
        *,
        provider: str,
        model: str,
        role: str,
        system_prompt: Optional[str] = None,
        user_content: str,
        response_text: str,
        usage: Optional[dict] = None,
        duration_seconds: Optional[float] = None,
        call_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """Log one LLM request/response with timestamp."""
        self._call_counter += 1
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "call_id": call_id or f"llm_{self._call_counter:04d}_{uuid.uuid4().hex[:8]}",
            "provider": provider,
            "model": model,
            "role": role,
            "input": {
                "system": system_prompt,
                "user": user_content,
            },
            "output": response_text,
            "usage": usage,
            "duration_seconds": duration_seconds,
        }
        if extra:
            record["extra"] = extra
        self._append_jsonl("llm_calls.jsonl", record)

    def log_node_created(
        self,
        *,
        node_id: str,
        claim_data: dict,
        source: str,
    ) -> None:
        """Log a graph node (claim) creation."""
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "node_id": node_id,
            "claim": claim_data,
            "source": source,
        }
        self._append_jsonl("nodes.jsonl", record)

    def log_edge_created(
        self,
        *,
        source_id: str,
        target_id: str,
        relation_type: str,
        confidence: float,
        source: str,
    ) -> None:
        """Log a graph edge (relation) creation."""
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "confidence": confidence,
            "source": source,
        }
        self._append_jsonl("edges.jsonl", record)

    def log_fallacy_added(
        self,
        *,
        fallacy_data: dict,
        source: str,
    ) -> None:
        """Log a fallacy annotation added to the graph."""
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "fallacy": fallacy_data,
            "source": source,
        }
        self._append_jsonl("fallacies.jsonl", record)

    def log_factcheck_added(
        self,
        *,
        factcheck_data: dict,
        source: str,
    ) -> None:
        """Log a fact-check result added to the graph."""
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "factcheck": factcheck_data,
            "source": source,
        }
        self._append_jsonl("factchecks.jsonl", record)

    def log_transcription_chunk(
        self,
        *,
        chunk_index: int,
        time_offset: float,
        segments: list[dict],
        raw_response_preview: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Log one transcription (STT) chunk output."""
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "chunk_index": chunk_index,
            "time_offset": time_offset,
            "segments_count": len(segments),
            "segments": segments,
            "raw_response_preview": raw_response_preview[:2000] if raw_response_preview else None,
            "duration_seconds": duration_seconds,
        }
        self._append_jsonl("transcription_chunks.jsonl", record)
