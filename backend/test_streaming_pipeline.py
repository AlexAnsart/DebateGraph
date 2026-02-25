"""
Test the LiveStreamingPipeline with real audio, simulating what happens when
a user uploads a video/audio file and the frontend streams chunks via WebSocket.

This script:
1. Loads demos/obama_romney_10min.mp3
2. Splits it into 15-second chunks (like MediaRecorder would)
3. Feeds each chunk through LiveStreamingPipeline.process_chunk()
4. Logs every graph update in real-time
5. Reports the full timeline and quality metrics

Usage:
    cd backend
    python test_streaming_pipeline.py
"""

import os
import sys
import asyncio
import logging
import time
import json
import io
from pathlib import Path

# Ensure backend is on path (for imports like api.models, pipeline.*, etc.)
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)  # Change to backend dir for relative imports

from dotenv import load_dotenv

# Try multiple .env locations (worktree vs main repo)
_env_candidates = [
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent.parent.parent.parent / ".env",
    Path("C:/Users/super/OneDrive/Desktop/DebateGraph/.env"),
]
for _ep in _env_candidates:
    if _ep.exists():
        load_dotenv(_ep, override=True)
        print(f"  Loaded .env from: {_ep}")
        break

# Main repo root (for demos folder etc.)
MAIN_REPO_ROOT = Path("C:/Users/super/OneDrive/Desktop/DebateGraph")

# Configure logging
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "streaming_test.log", mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger("streaming_test")


# -- Audio chunking ------------------------------------------------------------

def _get_ffmpeg_path() -> str | None:
    """Find ffmpeg binary — check PATH first, then imageio_ffmpeg."""
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _get_ffprobe_path() -> str | None:
    """Find ffprobe binary — check PATH first, then derive from ffmpeg path."""
    import shutil
    path = shutil.which("ffprobe")
    if path:
        return path
    ffmpeg = _get_ffmpeg_path()
    if ffmpeg:
        # Try replacing ffmpeg with ffprobe in the path
        probe = ffmpeg.replace("ffmpeg", "ffprobe")
        if os.path.exists(probe):
            return probe
    return None


def chunk_audio_file_with_ffmpeg(audio_path: str, chunk_duration_s: float = 15.0) -> list[tuple[bytes, float]]:
    """
    Split an audio file into chunks using ffmpeg subprocess.
    Each chunk is a valid MP3 file that OpenAI can process.
    """
    import subprocess
    import tempfile
    import glob as glob_module

    ffmpeg = _get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    logger.info(f"Splitting audio with ffmpeg: {audio_path}")
    logger.info(f"  ffmpeg binary: {ffmpeg}")

    # Get duration using ffprobe or ffmpeg
    ffprobe = _get_ffprobe_path()
    if ffprobe:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", audio_path],
            capture_output=True, text=True
        )
        total_duration = float(probe.stdout.strip())
    else:
        # Use ffmpeg to get duration
        probe = subprocess.run(
            [ffmpeg, "-i", audio_path, "-f", "null", "-"],
            capture_output=True, text=True
        )
        # Parse duration from stderr
        import re
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", probe.stderr)
        if match:
            h, m, s, cs = match.groups()
            total_duration = int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100
        else:
            total_duration = 600.0  # fallback

    logger.info(f"Audio duration: {total_duration:.1f}s ({total_duration/60:.1f} min)")

    # Create temp dir for chunks
    tmp_dir = tempfile.mkdtemp(prefix="debategraph_chunks_")

    # Split into chunks
    subprocess.run([
        ffmpeg, "-i", audio_path,
        "-f", "segment", "-segment_time", str(int(chunk_duration_s)),
        "-c:a", "libmp3lame", "-b:a", "32k",
        "-y", os.path.join(tmp_dir, "chunk_%04d.mp3")
    ], capture_output=True, check=True)

    # Read all chunk files
    chunk_files = sorted(glob_module.glob(os.path.join(tmp_dir, "chunk_*.mp3")))
    chunks = []
    for i, chunk_file in enumerate(chunk_files):
        with open(chunk_file, "rb") as f:
            chunk_bytes = f.read()
        time_offset = i * chunk_duration_s
        chunks.append((chunk_bytes, time_offset))
        os.unlink(chunk_file)

    os.rmdir(tmp_dir)
    logger.info(f"Split into {len(chunks)} chunks of ~{chunk_duration_s}s each (via ffmpeg)")
    return chunks


def chunk_audio_file(audio_path: str, chunk_duration_s: float = 15.0) -> list[tuple[bytes, float]]:
    """
    Split an audio file into chunks.
    Tries: ffmpeg > pydub > send whole file as one chunk.
    """
    # Try ffmpeg (from PATH or imageio_ffmpeg)
    if _get_ffmpeg_path():
        try:
            return chunk_audio_file_with_ffmpeg(audio_path, chunk_duration_s)
        except Exception as e:
            logger.warning(f"ffmpeg chunking failed: {e}")

    # Try pydub
    try:
        from pydub import AudioSegment
        logger.info(f"Loading audio with pydub: {audio_path}")
        audio = AudioSegment.from_file(audio_path)
        duration_s = len(audio) / 1000.0
        logger.info(f"Audio duration: {duration_s:.1f}s ({duration_s/60:.1f} min)")

        chunk_ms = int(chunk_duration_s * 1000)
        chunks = []
        offset = 0
        while offset < len(audio):
            end = min(offset + chunk_ms, len(audio))
            segment = audio[offset:end]
            buffer = io.BytesIO()
            segment.export(buffer, format="mp3", bitrate="32k")
            chunks.append((buffer.getvalue(), offset / 1000.0))
            offset = end
        logger.info(f"Split into {len(chunks)} chunks via pydub")
        return chunks
    except Exception as e:
        logger.warning(f"pydub failed: {e}")

    # Fallback: send entire file as a single chunk (still tests the pipeline)
    logger.warning("No audio splitting available — sending entire file as one chunk")
    with open(audio_path, "rb") as f:
        all_bytes = f.read()
    return [(all_bytes, 0.0)]


# -- Main test -----------------------------------------------------------------

async def main():
    logger.info("=" * 70)
    logger.info("  DebateGraph — Streaming Pipeline Test")
    logger.info("  Simulates real-time chunked audio processing")
    logger.info("=" * 70)

    # Check environment
    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    logger.info(f"  OPENAI_API_KEY:    {'set' if openai_key else 'MISSING'}")
    logger.info(f"  ANTHROPIC_API_KEY: {'set' if anthropic_key else 'MISSING'}")

    if not openai_key:
        logger.error("OPENAI_API_KEY required. Aborting.")
        sys.exit(1)
    if not anthropic_key:
        logger.error("ANTHROPIC_API_KEY required. Aborting.")
        sys.exit(1)

    # Find demo audio (check worktree first, then main repo)
    demo_audio = Path(__file__).parent.parent / "demos" / "obama_romney_10min.mp3"
    if not demo_audio.exists():
        demo_audio = MAIN_REPO_ROOT / "demos" / "obama_romney_10min.mp3"
    if not demo_audio.exists():
        logger.error(f"Demo audio not found. Searched:")
        logger.error(f"  {Path(__file__).parent.parent / 'demos' / 'obama_romney_10min.mp3'}")
        logger.error(f"  {MAIN_REPO_ROOT / 'demos' / 'obama_romney_10min.mp3'}")
        sys.exit(1)

    file_size_mb = demo_audio.stat().st_size / (1024 * 1024)
    logger.info(f"  Audio file: {demo_audio.name} ({file_size_mb:.1f} MB)")

    # -- Split audio into chunks ----------------------------------------------
    CHUNK_DURATION_S = 15.0
    chunks = chunk_audio_file(str(demo_audio), CHUNK_DURATION_S)
    total_chunks = len(chunks)

    # -- Track all updates ----------------------------------------------------
    updates = []
    graph_snapshots = []
    chunk_timings = []

    async def on_update(message: dict):
        """Callback that receives all pipeline updates (like WebSocket.send_json)."""
        msg_type = message.get("type", "?")
        updates.append(message)

        if msg_type == "stream_started":
            logger.info(f"  >>> Stream started: session={message.get('session_id')}")

        elif msg_type == "chunk_received":
            ci = message.get("chunk_index", "?")
            sz = message.get("size_bytes", 0)
            logger.info(f"  >>> Chunk {ci} received ({sz/1024:.1f} KB)")

        elif msg_type == "transcription_update":
            ci = message.get("chunk_index", "?")
            n_segs = len(message.get("new_segments", []))
            total = message.get("total_segments", 0)
            logger.info(f"  >>> Transcription update: chunk {ci}, +{n_segs} segments (total: {total})")
            # Log segment content
            for seg in message.get("new_segments", [])[:3]:
                speaker = seg.get("speaker", "?")
                text = seg.get("text", "")[:80]
                logger.info(f"      [{speaker}] {text}")

        elif msg_type == "graph_update":
            ci = message.get("chunk_index", "?")
            stats = message.get("stats", {})
            logger.info(
                f"  >>> GRAPH UPDATE: chunk {ci} — "
                f"{stats.get('nodes', 0)} nodes, "
                f"{stats.get('edges', 0)} edges, "
                f"{stats.get('fallacies', 0)} fallacies, "
                f"{stats.get('factchecks', 0)} factchecks"
            )
            graph_snapshots.append(message.get("graph"))

        elif msg_type == "finalizing":
            logger.info(f"  >>> Finalizing: {message.get('message', '')}")

        elif msg_type == "stream_complete":
            nodes = len(message.get("graph", {}).get("nodes", []))
            edges = len(message.get("graph", {}).get("edges", []))
            logger.info(f"  >>> STREAM COMPLETE: {nodes} nodes, {edges} edges")

        elif msg_type == "error":
            logger.error(f"  >>> ERROR: stage={message.get('stage')}, {message.get('message')}")

    # -- Initialize pipeline --------------------------------------------------
    from pipeline.streaming_pipeline import LiveStreamingPipeline

    pipeline = LiveStreamingPipeline(
        on_update=on_update,
        session_id="stream_test",
        enable_factcheck=True,
        enable_llm_fallacy=True,
    )

    logger.info("\n" + "=" * 70)
    logger.info("  Starting streaming pipeline...")
    logger.info(f"  Chunk duration: {CHUNK_DURATION_S}s")
    logger.info(f"  Total chunks: {total_chunks}")
    logger.info("=" * 70)

    await pipeline.start()

    # -- Feed chunks ----------------------------------------------------------
    total_start = time.time()

    for i, (chunk_bytes, time_offset) in enumerate(chunks):
        chunk_start = time.time()
        logger.info(f"\n{'-' * 50}")
        logger.info(f"  CHUNK {i}/{total_chunks-1} (offset={time_offset:.1f}s, {len(chunk_bytes)/1024:.1f} KB)")
        logger.info(f"{'-' * 50}")

        await pipeline.process_chunk(
            audio_bytes=chunk_bytes,
            chunk_index=i,
            time_offset=time_offset,
            filename=f"chunk_{i}.mp3",
        )

        chunk_time = time.time() - chunk_start
        chunk_timings.append(chunk_time)
        elapsed = time.time() - total_start
        logger.info(
            f"  Chunk {i} done in {chunk_time:.1f}s "
            f"(elapsed: {elapsed:.1f}s, "
            f"latency ratio: {chunk_time/CHUNK_DURATION_S:.2f}x)"
        )

        # Small delay between chunks to simulate real-time playback pacing
        # In real usage, chunks arrive every 15s, so we don't need to wait the full 15s,
        # but a tiny delay prevents hammering the APIs
        if i < total_chunks - 1:
            await asyncio.sleep(0.5)

    # -- Finalize -------------------------------------------------------------
    logger.info(f"\n{'=' * 70}")
    logger.info("  Finalizing stream...")
    final_snapshot = await pipeline.finalize()
    total_time = time.time() - total_start

    # -- Results --------------------------------------------------------------
    logger.info(f"\n{'=' * 70}")
    logger.info("  STREAMING PIPELINE TEST RESULTS")
    logger.info(f"{'=' * 70}")

    logger.info(f"\n  TIMING:")
    logger.info(f"    Total time:           {total_time:.1f}s ({total_time/60:.1f} min)")
    logger.info(f"    Audio duration:       {total_chunks * CHUNK_DURATION_S:.0f}s")
    logger.info(f"    Avg chunk latency:    {sum(chunk_timings)/len(chunk_timings):.1f}s")
    logger.info(f"    Max chunk latency:    {max(chunk_timings):.1f}s")
    logger.info(f"    Min chunk latency:    {min(chunk_timings):.1f}s")
    logger.info(f"    Real-time ratio:      {total_time / (total_chunks * CHUNK_DURATION_S):.2f}x")
    logger.info(f"    Chunks processed:     {total_chunks}")

    logger.info(f"\n  GRAPH:")
    logger.info(f"    Final nodes:          {len(final_snapshot.nodes)}")
    logger.info(f"    Final edges:          {len(final_snapshot.edges)}")
    logger.info(f"    Fallacies:            {sum(len(n.fallacies) for n in final_snapshot.nodes)}")
    logger.info(f"    Fact-checks:          {len([n for n in final_snapshot.nodes if n.factcheck_verdict.value != 'pending'])}")
    logger.info(f"    Cycles:               {len(final_snapshot.cycles_detected)}")
    logger.info(f"    Graph updates sent:   {len(graph_snapshots)}")

    # Per-chunk graph growth
    logger.info(f"\n  GRAPH GROWTH OVER TIME:")
    for idx, snap in enumerate(graph_snapshots):
        if snap:
            nodes = len(snap.get("nodes", []))
            edges = len(snap.get("edges", []))
            logger.info(f"    After chunk {idx}: {nodes} nodes, {edges} edges")

    # Speakers
    speakers = set()
    for node in final_snapshot.nodes:
        speakers.add(node.speaker)
    logger.info(f"\n  SPEAKERS: {sorted(speakers)}")

    # Rigor scores
    if final_snapshot.rigor_scores:
        logger.info(f"\n  RIGOR SCORES:")
        for score in sorted(final_snapshot.rigor_scores, key=lambda s: s.overall_score, reverse=True):
            logger.info(f"    {score.speaker}: {score.overall_score:.2%}")

    # Fallacy details
    all_fallacies = [f for n in final_snapshot.nodes for f in n.fallacies]
    if all_fallacies:
        from collections import Counter
        fallacy_types = Counter(f.fallacy_type.value for f in all_fallacies)
        logger.info(f"\n  FALLACY TYPES:")
        for ftype, count in fallacy_types.most_common():
            logger.info(f"    {ftype}: {count}")

    # Claim types
    from collections import Counter
    claim_types = Counter(n.claim_type.value for n in final_snapshot.nodes)
    logger.info(f"\n  CLAIM TYPES:")
    for ctype, count in claim_types.most_common():
        logger.info(f"    {ctype}: {count}")

    # Sample claims
    logger.info(f"\n  SAMPLE CLAIMS (first 10):")
    for node in final_snapshot.nodes[:10]:
        text = node.label[:80] if node.label else node.full_text[:80]
        logger.info(f"    [{node.speaker}] ({node.claim_type.value}) {text}")
        if node.fallacies:
            for f in node.fallacies:
                logger.info(f"      ^ FALLACY: {f.fallacy_type.value} (severity={f.severity:.2f})")

    # Save final snapshot
    snapshot_path = log_dir / "streaming_test_snapshot.json"
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(final_snapshot.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        logger.info(f"\n  Snapshot saved: {snapshot_path}")
    except Exception as e:
        logger.error(f"  Failed to save snapshot: {e}")

    # Save timing data
    timing_path = log_dir / "streaming_test_timing.json"
    try:
        with open(timing_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_time_s": total_time,
                "chunk_duration_s": CHUNK_DURATION_S,
                "total_chunks": total_chunks,
                "chunk_timings_s": chunk_timings,
                "avg_latency_s": sum(chunk_timings) / len(chunk_timings),
                "max_latency_s": max(chunk_timings),
                "realtime_ratio": total_time / (total_chunks * CHUNK_DURATION_S),
                "final_nodes": len(final_snapshot.nodes),
                "final_edges": len(final_snapshot.edges),
                "graph_update_count": len(graph_snapshots),
            }, f, indent=2)
        logger.info(f"  Timing data saved: {timing_path}")
    except Exception as e:
        logger.error(f"  Failed to save timing: {e}")

    logger.info(f"\n{'=' * 70}")
    logger.info("  TEST COMPLETE")
    logger.info(f"{'=' * 70}")

    return final_snapshot


if __name__ == "__main__":
    asyncio.run(main())
