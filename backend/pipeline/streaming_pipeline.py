"""
Live Streaming Pipeline — Incremental argument graph construction.

Designed for real-time audio input:
- Processes audio chunks of ~15s as they arrive
- Transcribes each chunk via OpenAI gpt-4o-transcribe (fast, ~2-3s)
- Extracts claims from NEW segments only (incremental)
- Runs structural fallacy detection immediately
- Runs LLM fallacy detection on new claims (async)
- Runs fact-checking in background (non-blocking)
- Merges results into a shared DebateGraphStore
- Emits graph_update events via callback

Architecture:
  AudioChunk (bytes) -> transcribe -> new segments
                     -> OntologicalAgent (new segs only)
                     -> SkepticAgent (structural, instant)
                     -> [async] SkepticAgent LLM
                     -> [async] ResearcherAgent
                     -> callback(snapshot_delta)
"""

import os
import io
import time
import asyncio
import logging
import tempfile
from typing import Callable, Awaitable, Optional
from pathlib import Path

from api.models.schemas import (
    TranscriptionResult,
    TranscriptionSegment,
    GraphSnapshot,
)
from graph.store import DebateGraphStore
from agents.ontological import OntologicalAgent
from agents.skeptic import SkepticAgent
from agents.researcher import ResearcherAgent

logger = logging.getLogger("debategraph.streaming")


# ─── Speaker tracking ────────────────────────────────────────────────────────

class SpeakerReconciler:
    """
    Reconciles speaker IDs across chunks.

    OpenAI's diarized model assigns arbitrary speaker IDs per chunk
    (e.g., SPEAKER_24, SPEAKER_83). We need to map them to consistent
    canonical IDs (SPEAKER_00, SPEAKER_01, ...) across the whole stream.

    Heuristic: within a chunk, speakers are numbered in order of appearance.
    We map them to canonical IDs based on their position in the chunk and
    continuity from the previous chunk's last speaker.
    """
    def __init__(self):
        # Map from raw per-chunk speaker IDs to canonical IDs
        self._canonical_map: dict[str, str] = {}
        # Canonical speakers in order of first appearance
        self._canonical_speakers: list[str] = []
        # Track which raw IDs appear in each chunk for ordering
        self._chunk_raw_order: list[str] = []
        self._last_canonical: str | None = None

    def reconcile(self, raw_speaker: str) -> str:
        """Map a raw per-chunk speaker ID to a canonical speaker ID."""
        if raw_speaker in self._canonical_map:
            canonical = self._canonical_map[raw_speaker]
            self._last_canonical = canonical
            return canonical

        # New raw speaker — assign canonical ID
        if not self._canonical_speakers:
            # First speaker ever
            canonical = "SPEAKER_00"
        elif self._last_canonical and len(self._canonical_speakers) == 1:
            # Second speaker appears — they're definitely different
            canonical = "SPEAKER_01"
        else:
            # Additional speaker — assign next canonical ID
            idx = len(self._canonical_speakers)
            canonical = f"SPEAKER_{idx:02d}"

        self._canonical_map[raw_speaker] = canonical
        if canonical not in self._canonical_speakers:
            self._canonical_speakers.append(canonical)
        self._last_canonical = canonical
        return canonical

    def start_new_chunk(self, chunk_speakers: list[str]) -> None:
        """
        Called at the start of each new chunk with the raw speaker IDs
        found in that chunk (in order of appearance).

        For chunks after the first, we try to map speakers based on
        the assumption that chunks with 2 speakers usually have the same
        2 canonical speakers, just with different raw IDs.
        """
        if not chunk_speakers:
            return

        # If we have 2 canonical speakers and 2 chunk speakers,
        # map based on speaking order continuity
        if len(self._canonical_speakers) >= 2 and len(chunk_speakers) >= 2:
            # The first speaker in a new chunk is likely continuing from
            # where the last chunk left off (or the other speaker responding)
            first_raw = chunk_speakers[0]
            second_raw = chunk_speakers[1] if len(chunk_speakers) > 1 else None

            if first_raw not in self._canonical_map:
                # Assign first speaker based on who spoke last
                if self._last_canonical == self._canonical_speakers[0]:
                    # Last chunk ended with SPEAKER_00, this chunk probably
                    # starts with SPEAKER_01 (new turn) or SPEAKER_00 (continuation)
                    # Default: treat new chunk first speaker as SPEAKER_00
                    self._canonical_map[first_raw] = self._canonical_speakers[0]
                else:
                    self._canonical_map[first_raw] = self._canonical_speakers[1] if len(self._canonical_speakers) > 1 else self._canonical_speakers[0]

            if second_raw and second_raw not in self._canonical_map:
                # Second speaker is the other one
                first_canonical = self._canonical_map.get(first_raw)
                if first_canonical == self._canonical_speakers[0]:
                    self._canonical_map[second_raw] = self._canonical_speakers[1]
                else:
                    self._canonical_map[second_raw] = self._canonical_speakers[0]

    @property
    def num_speakers(self) -> int:
        return len(self._canonical_speakers)


# ─── Streaming Pipeline ───────────────────────────────────────────────────────

class LiveStreamingPipeline:
    """
    Incremental pipeline for live audio streaming.

    Usage:
        pipeline = LiveStreamingPipeline(on_update=my_callback)
        await pipeline.start(session_id="live-123")
        await pipeline.process_chunk(audio_bytes, chunk_index=0, time_offset=0.0)
        await pipeline.finalize()
    """

    def __init__(
        self,
        on_update: Callable[[dict], Awaitable[None]],
        session_id: str = None,
        enable_factcheck: bool = True,
        enable_llm_fallacy: bool = True,
    ):
        self.on_update = on_update
        self.session_id = session_id or f"live_{int(time.time())}"
        self.enable_factcheck = enable_factcheck
        self.enable_llm_fallacy = enable_llm_fallacy

        # Shared state
        self.graph_store = DebateGraphStore()
        self.all_segments: list[TranscriptionSegment] = []
        self.processed_segment_count = 0
        self.chunk_count = 0
        self.start_time = 0.0

        # Speaker reconciliation across chunks
        self._speaker_reconciler = SpeakerReconciler()

        # Buffer for merging tiny chunks
        self._leftover_bytes: bytes = b""
        self._leftover_offset: float = 0.0
        self._min_chunk_bytes = 2000  # Skip chunks smaller than 2KB

        # Agents (initialized lazily)
        self._ontological: Optional[OntologicalAgent] = None
        self._skeptic: Optional[SkepticAgent] = None
        self._researcher: Optional[ResearcherAgent] = None

        # Background tasks
        self._bg_tasks: list[asyncio.Task] = []

        # OpenAI client
        self._openai_client = None

    async def start(self):
        """Initialize the pipeline."""
        self.start_time = time.time()
        logger.info(f"[{self.session_id}] Live streaming pipeline started")

        # Initialize agents
        self._ontological = OntologicalAgent()
        self._skeptic = SkepticAgent()
        if self.enable_factcheck:
            self._researcher = ResearcherAgent()

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=api_key)
            logger.info(f"[{self.session_id}] OpenAI async client initialized")
        else:
            logger.warning(f"[{self.session_id}] No OPENAI_API_KEY — transcription unavailable")

        # Send initial state
        await self.on_update({
            "type": "stream_started",
            "session_id": self.session_id,
            "timestamp": time.time(),
        })

    async def process_chunk(
        self,
        audio_bytes: bytes,
        chunk_index: int,
        time_offset: float = 0.0,
        filename: str = "chunk.webm",
    ) -> None:
        """
        Process a single audio chunk.
        Called each time a new audio chunk arrives from the client.

        Args:
            audio_bytes: Raw audio data (WebM, MP3, WAV, etc.)
            chunk_index: Sequential chunk number
            time_offset: Start time of this chunk in the overall stream (seconds)
            filename: Filename hint for OpenAI API (determines format)
        """
        self.chunk_count += 1
        chunk_start = time.time()

        logger.info(
            f"[{self.session_id}] Processing chunk {chunk_index} "
            f"({len(audio_bytes)/1024:.1f} KB, offset={time_offset:.1f}s)"
        )

        # Skip tiny chunks (< 2KB) — they're too small for transcription
        # and usually just silence or the tail end of a stream
        if len(audio_bytes) < self._min_chunk_bytes:
            logger.info(
                f"[{self.session_id}] Chunk {chunk_index} too small "
                f"({len(audio_bytes)} bytes < {self._min_chunk_bytes}), skipping"
            )
            return

        # Notify frontend: chunk received
        await self.on_update({
            "type": "chunk_received",
            "chunk_index": chunk_index,
            "size_bytes": len(audio_bytes),
            "time_offset": time_offset,
        })

        # Step 1: Transcribe
        try:
            new_segments = await self._transcribe_chunk(
                audio_bytes, time_offset, filename
            )
        except Exception as e:
            logger.error(f"[{self.session_id}] Transcription failed for chunk {chunk_index}: {e}")
            await self.on_update({
                "type": "error",
                "stage": "transcription",
                "chunk_index": chunk_index,
                "message": str(e),
            })
            return

        if not new_segments:
            logger.info(f"[{self.session_id}] Chunk {chunk_index}: no segments transcribed")
            return

        # Add to full transcript
        self.all_segments.extend(new_segments)

        # Notify: transcription done
        await self.on_update({
            "type": "transcription_update",
            "chunk_index": chunk_index,
            "new_segments": [s.model_dump() for s in new_segments],
            "total_segments": len(self.all_segments),
        })

        logger.info(
            f"[{self.session_id}] Chunk {chunk_index}: "
            f"{len(new_segments)} new segments transcribed in {time.time()-chunk_start:.1f}s"
        )

        # Step 2: Extract claims from new segments only
        try:
            await self._extract_claims(new_segments, chunk_index)
        except Exception as e:
            logger.error(f"[{self.session_id}] Claim extraction failed: {e}", exc_info=True)

        # Step 3: Structural fallacy detection (instant, no LLM)
        try:
            await self._detect_structural_fallacies()
        except Exception as e:
            logger.error(f"[{self.session_id}] Structural fallacy detection failed: {e}")

        # Step 4: Emit graph update
        await self._emit_graph_update(chunk_index)

        # Step 5: Background tasks (LLM fallacy + fact-check)
        if self.enable_llm_fallacy and self._skeptic and self._skeptic.client:
            task = asyncio.create_task(
                self._run_llm_fallacy_bg(chunk_index)
            )
            self._bg_tasks.append(task)

        if self.enable_factcheck and self._researcher:
            task = asyncio.create_task(
                self._run_factcheck_bg(chunk_index)
            )
            self._bg_tasks.append(task)

        logger.info(
            f"[{self.session_id}] Chunk {chunk_index} processed in "
            f"{time.time()-chunk_start:.1f}s total"
        )

    async def finalize(self) -> GraphSnapshot:
        """
        Finalize the stream: wait for background tasks, compute rigor scores,
        persist to DB, return final snapshot.
        """
        logger.info(
            f"[{self.session_id}] Finalizing stream "
            f"({self._speaker_reconciler.num_speakers} speakers reconciled)"
        )

        await self.on_update({
            "type": "finalizing",
            "message": "Computing final analysis...",
        })

        # Wait for all background tasks (with timeout)
        if self._bg_tasks:
            pending = [t for t in self._bg_tasks if not t.done()]
            if pending:
                logger.info(f"[{self.session_id}] Waiting for {len(pending)} background tasks...")
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=60.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"[{self.session_id}] Background tasks timed out")

        # Compute rigor scores
        rigor_scores = self.graph_store.compute_rigor_scores()

        # Final snapshot
        snapshot = self.graph_store.to_snapshot()

        total_time = time.time() - self.start_time
        logger.info(
            f"[{self.session_id}] Stream finalized: "
            f"{len(snapshot.nodes)} nodes, {len(snapshot.edges)} edges, "
            f"{sum(len(n.fallacies) for n in snapshot.nodes)} fallacies, "
            f"{len([n for n in snapshot.nodes if n.factcheck_verdict.value != 'pending'])} factchecks "
            f"in {total_time:.1f}s"
        )

        await self.on_update({
            "type": "stream_complete",
            "session_id": self.session_id,
            "total_time": total_time,
            "graph": snapshot.model_dump(mode="json"),
            "transcription": {
                "segments": [s.model_dump() for s in self.all_segments],
                "language": "en",
                "num_speakers": len(set(s.speaker for s in self.all_segments)),
            },
        })

        return snapshot

    # ─── Private helpers ─────────────────────────────────────────────────────

    async def _transcribe_chunk(
        self,
        audio_bytes: bytes,
        time_offset: float,
        filename: str,
    ) -> list[TranscriptionSegment]:
        """Transcribe a chunk using OpenAI gpt-4o-transcribe-diarize."""
        if not self._openai_client:
            raise RuntimeError("OpenAI client not initialized")

        # Write to temp file (OpenAI API requires a file-like object with name)
        suffix = Path(filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                # Try diarized first for speaker attribution
                try:
                    transcript = await self._openai_client.audio.transcriptions.create(
                        model="gpt-4o-transcribe-diarize",
                        file=(filename, f, "audio/webm"),
                        response_format="diarized_json",
                        chunking_strategy="auto",
                    )
                    segments = self._parse_diarized_response(transcript, time_offset)
                    if segments:
                        return segments
                except Exception as e:
                    logger.warning(f"Diarized transcription failed, falling back: {e}")
                    f.seek(0)

                # Fallback: standard transcription with timestamps
                transcript = await self._openai_client.audio.transcriptions.create(
                    model="gpt-4o-transcribe",
                    file=(filename, f, "audio/webm"),
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
                return self._parse_verbose_response(transcript, time_offset)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _parse_diarized_response(
        self, transcript, time_offset: float
    ) -> list[TranscriptionSegment]:
        """Parse diarized_json response with speaker reconciliation."""
        from pipeline.transcription import _normalize_speaker
        segments = []

        if hasattr(transcript, "segments") and transcript.segments:
            # Collect raw speaker IDs in order of first appearance
            raw_speakers_order = []
            for seg in transcript.segments:
                raw_sp = _normalize_speaker(getattr(seg, "speaker", "SPEAKER_00") or "SPEAKER_00")
                if raw_sp not in raw_speakers_order:
                    raw_speakers_order.append(raw_sp)

            # Inform reconciler about this chunk's speakers
            self._speaker_reconciler.start_new_chunk(raw_speakers_order)

            for seg in transcript.segments:
                text = getattr(seg, "text", "").strip()
                if not text or len(text.split()) < 3:
                    continue
                raw_speaker = _normalize_speaker(getattr(seg, "speaker", "SPEAKER_00") or "SPEAKER_00")
                # Reconcile to canonical speaker ID
                speaker = self._speaker_reconciler.reconcile(raw_speaker)
                start = float(getattr(seg, "start", 0.0)) + time_offset
                end = float(getattr(seg, "end", 0.0)) + time_offset
                segments.append(TranscriptionSegment(
                    speaker=speaker,
                    text=text,
                    start=round(start, 2),
                    end=round(end, 2),
                ))
        return segments

    def _parse_verbose_response(
        self, transcript, time_offset: float
    ) -> list[TranscriptionSegment]:
        """Parse verbose_json response (no diarization — single speaker)."""
        segments = []
        # Determine speaker from context (use last known or SPEAKER_00)
        speaker = "SPEAKER_00"
        if self.all_segments:
            speaker = self.all_segments[-1].speaker

        if hasattr(transcript, "segments") and transcript.segments:
            for seg in transcript.segments:
                text = getattr(seg, "text", "").strip()
                if not text or len(text.split()) < 3:
                    continue
                start = float(getattr(seg, "start", 0.0)) + time_offset
                end = float(getattr(seg, "end", 0.0)) + time_offset
                segments.append(TranscriptionSegment(
                    speaker=speaker,
                    text=text,
                    start=round(start, 2),
                    end=round(end, 2),
                ))
        elif hasattr(transcript, "text") and transcript.text:
            # No segment timestamps — create one segment for the whole chunk
            text = transcript.text.strip()
            if text:
                segments.append(TranscriptionSegment(
                    speaker=speaker,
                    text=text,
                    start=round(time_offset, 2),
                    end=round(time_offset + 15.0, 2),
                ))
        return segments

    async def _extract_claims(
        self,
        new_segments: list[TranscriptionSegment],
        chunk_index: int,
    ) -> None:
        """Extract claims from new segments and add to graph store."""
        if not new_segments or not self._ontological:
            return

        # Build a mini-transcription from new segments only
        mini_transcription = TranscriptionResult(
            segments=new_segments,
            language="en",
            num_speakers=len(set(s.speaker for s in new_segments)),
        )

        # Use chunk_index as prefix to avoid ID collisions
        # Temporarily override the chunk_idx in the agent
        prev_count = self.graph_store.num_nodes
        await self._ontological._extract_chunk(
            new_segments,
            self.graph_store,
            chunk_idx=self.chunk_count * 100 + chunk_index,
        )
        new_nodes = self.graph_store.num_nodes - prev_count
        logger.info(
            f"[{self.session_id}] Chunk {chunk_index}: "
            f"+{new_nodes} nodes (total: {self.graph_store.num_nodes})"
        )

    async def _detect_structural_fallacies(self) -> None:
        """Run structural fallacy detection (no LLM, instant)."""
        if not self._skeptic:
            return
        structural = self._skeptic._detect_structural_fallacies(self.graph_store)
        # Only add new ones (avoid duplicates)
        existing = {
            (f.claim_id, f.fallacy_type)
            for f in self.graph_store.get_all_fallacies()
        }
        for f in structural:
            if (f.claim_id, f.fallacy_type) not in existing:
                self.graph_store.add_fallacy(f)

    async def _emit_graph_update(self, chunk_index: int) -> None:
        """Emit current graph state to frontend."""
        snapshot = self.graph_store.to_snapshot()
        await self.on_update({
            "type": "graph_update",
            "chunk_index": chunk_index,
            "graph": snapshot.model_dump(mode="json"),
            "transcription": {
                "segments": [s.model_dump() for s in self.all_segments],
                "language": "en",
                "num_speakers": len(set(s.speaker for s in self.all_segments)),
            },
            "stats": {
                "nodes": len(snapshot.nodes),
                "edges": len(snapshot.edges),
                "fallacies": sum(len(n.fallacies) for n in snapshot.nodes),
                "factchecks": len([n for n in snapshot.nodes if n.factcheck_verdict.value != "pending"]),
            },
        })

    async def _run_llm_fallacy_bg(self, chunk_index: int) -> None:
        """Background: run LLM fallacy detection on recent claims."""
        try:
            # Get claims added in this chunk (last N claims)
            all_claims = self.graph_store.get_all_claims()
            # Process only the last 15 claims (most recent chunk)
            recent_claims = all_claims[-15:] if len(all_claims) > 15 else all_claims
            if not recent_claims:
                return

            llm_fallacies = await self._skeptic._detect_chunk(recent_claims, self.graph_store)
            existing = {
                (f.claim_id, f.fallacy_type)
                for f in self.graph_store.get_all_fallacies()
            }
            new_count = 0
            for f in llm_fallacies:
                if (f.claim_id, f.fallacy_type) not in existing:
                    self.graph_store.add_fallacy(f)
                    new_count += 1

            if new_count > 0:
                logger.info(
                    f"[{self.session_id}] BG fallacy: +{new_count} LLM fallacies"
                )
                await self._emit_graph_update(chunk_index)
        except Exception as e:
            logger.error(f"[{self.session_id}] BG LLM fallacy failed: {e}")

    async def _run_factcheck_bg(self, chunk_index: int) -> None:
        """Background: fact-check new factual claims."""
        try:
            all_claims = self.graph_store.get_all_claims()
            # Only check claims not yet fact-checked
            unchecked = [
                c for c in all_claims
                if c.is_factual and c.id not in self.graph_store._factchecks
            ]
            if not unchecked:
                return

            # Limit to 5 per chunk to avoid rate limits
            to_check = unchecked[:5]
            logger.info(
                f"[{self.session_id}] BG fact-check: {len(to_check)} claims"
            )

            semaphore = asyncio.Semaphore(3)
            async def check_one(claim):
                async with semaphore:
                    return await self._researcher.check_claim(claim)

            results = await asyncio.gather(
                *[check_one(c) for c in to_check],
                return_exceptions=True,
            )
            new_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Fact-check error: {result}")
                    continue
                self.graph_store.add_factcheck(result)
                new_count += 1

            if new_count > 0:
                logger.info(
                    f"[{self.session_id}] BG fact-check: +{new_count} verdicts"
                )
                await self._emit_graph_update(chunk_index)
        except Exception as e:
            logger.error(f"[{self.session_id}] BG fact-check failed: {e}")
