"""
Standalone pipeline test script.
Runs the full DebateGraph pipeline on demos/obama_romney_10min.mp3
using real API calls (OpenAI, Anthropic, Tavily) and persists to PostgreSQL.

Usage:
    cd backend
    python run_pipeline_test.py
"""

import os
import sys
import asyncio
import logging
import time
import json
from pathlib import Path

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Configure rich logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "pipeline_test.log", mode="w", encoding="utf-8"),
    ]
)
logger = logging.getLogger("pipeline_test")

# Ensure logs dir exists
(Path(__file__).parent.parent / "logs").mkdir(exist_ok=True)


async def main():
    logger.info("=" * 70)
    logger.info("  DebateGraph — Full Pipeline Test")
    logger.info("=" * 70)

    # ── Check environment ──────────────────────────────────────────────────
    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    db_url = os.getenv("DATABASE_URL", "")

    logger.info(f"  OPENAI_API_KEY:    {'✓ set' if openai_key else '✗ MISSING'}")
    logger.info(f"  ANTHROPIC_API_KEY: {'✓ set' if anthropic_key else '✗ MISSING'}")
    logger.info(f"  TAVILY_API_KEY:    {'✓ set' if tavily_key else '✗ MISSING'}")
    logger.info(f"  DATABASE_URL:      {'✓ set' if db_url else '✗ MISSING'}")

    if not openai_key:
        logger.error("OPENAI_API_KEY is required for transcription. Aborting.")
        sys.exit(1)
    if not anthropic_key:
        logger.error("ANTHROPIC_API_KEY is required for analysis. Aborting.")
        sys.exit(1)

    # ── Find demo audio ────────────────────────────────────────────────────
    demo_audio = Path(__file__).parent.parent / "demos" / "obama_romney_10min.mp3"
    if not demo_audio.exists():
        logger.error(f"Demo audio not found: {demo_audio}")
        sys.exit(1)

    file_size_mb = demo_audio.stat().st_size / (1024 * 1024)
    logger.info(f"\n  Audio file: {demo_audio.name} ({file_size_mb:.1f} MB)")
    logger.info("=" * 70)

    # ── Initialize DB ──────────────────────────────────────────────────────
    logger.info("\n[0/5] Initializing PostgreSQL...")
    try:
        from db.database import init_db, create_job, update_job_status, save_snapshot, get_job, list_jobs
        init_db()
        logger.info("  ✓ PostgreSQL tables ready")
    except Exception as e:
        logger.error(f"  ✗ DB init failed: {e}")
        logger.warning("  Continuing without DB persistence...")
        init_db = create_job = update_job_status = save_snapshot = get_job = list_jobs = None

    # ── Create job ─────────────────────────────────────────────────────────
    import uuid
    job_id = str(uuid.uuid4())
    logger.info(f"\n  Job ID: {job_id}")

    if create_job:
        # source_path enables media serving from demos/ on remote (no uploads/)
        create_job(job_id, audio_filename=demo_audio.name, source_path=f"demos/{demo_audio.name}")
        logger.info("  ✓ Job created in DB")

    # ── Step 1: Transcription ──────────────────────────────────────────────
    logger.info("\n[1/5] TRANSCRIPTION (OpenAI gpt-4o-transcribe-diarize)...")
    t_start = time.time()

    if update_job_status:
        update_job_status(job_id, "transcribing", progress=0.1)

    try:
        from pipeline.transcription import transcribe_audio
        transcription = await asyncio.to_thread(transcribe_audio, str(demo_audio))
        t_transcription = time.time() - t_start

        logger.info(f"  ✓ Transcription complete in {t_transcription:.1f}s")
        logger.info(f"    Segments:  {len(transcription.segments)}")
        logger.info(f"    Speakers:  {transcription.num_speakers}")
        logger.info(f"    Language:  {transcription.language}")

        # Log first 5 segments
        logger.info("\n  First 5 segments:")
        for i, seg in enumerate(transcription.segments[:5]):
            logger.info(f"    [{seg.start:.1f}s-{seg.end:.1f}s] {seg.speaker}: {seg.text[:80]}")

        # Log speaker distribution
        from collections import Counter
        speaker_counts = Counter(seg.speaker for seg in transcription.segments)
        logger.info(f"\n  Speaker distribution: {dict(speaker_counts)}")

    except Exception as e:
        logger.error(f"  ✗ Transcription failed: {e}", exc_info=True)
        if update_job_status:
            update_job_status(job_id, "error", error=str(e))
        sys.exit(1)

    if update_job_status:
        update_job_status(job_id, "transcribing", progress=0.5)

    # ── Step 2: Analysis Pipeline ──────────────────────────────────────────
    logger.info("\n[2/5] ANALYSIS PIPELINE (Ontological + Skeptic + Researcher)...")
    t_analysis_start = time.time()

    if update_job_status:
        update_job_status(job_id, "extracting", progress=0.6)

    try:
        from graph.store import DebateGraphStore
        from agents.orchestrator import run_analysis_pipeline

        graph_store = DebateGraphStore()
        snapshot = await run_analysis_pipeline(transcription, graph_store, session_id=job_id)
        t_analysis = time.time() - t_analysis_start

        logger.info(f"\n  ✓ Analysis complete in {t_analysis:.1f}s")
        logger.info(f"    Nodes (claims):    {len(snapshot.nodes)}")
        logger.info(f"    Edges (relations): {len(snapshot.edges)}")
        logger.info(f"    Fallacies:         {sum(len(n.fallacies) for n in snapshot.nodes)}")
        logger.info(f"    Fact-checked:      {len([n for n in snapshot.nodes if n.factcheck_verdict.value != 'pending'])}")
        logger.info(f"    Cycles detected:   {len(snapshot.cycles_detected)}")

    except Exception as e:
        logger.error(f"  ✗ Analysis pipeline failed: {e}", exc_info=True)
        if update_job_status:
            update_job_status(job_id, "error", error=str(e))
        sys.exit(1)

    # ── Step 3: Persist to DB ──────────────────────────────────────────────
    logger.info("\n[3/5] PERSISTING TO POSTGRESQL...")
    if save_snapshot:
        try:
            snapshot_dict = snapshot.model_dump(mode="json")
            transcription_dict = transcription.model_dump(mode="json")
            snapshot_id = save_snapshot(job_id, snapshot_dict, transcription_dict)
            update_job_status(job_id, "complete", progress=1.0)
            logger.info(f"  ✓ Snapshot saved: {snapshot_id}")
        except Exception as e:
            logger.error(f"  ✗ DB save failed: {e}", exc_info=True)
    else:
        logger.warning("  ⚠ DB not available, skipping persistence")

    # ── Step 4: Detailed Results ───────────────────────────────────────────
    logger.info("\n[4/5] DETAILED RESULTS")
    logger.info("=" * 70)

    # Rigor scores
    logger.info("\n  RIGOR SCORES:")
    for score in sorted(snapshot.rigor_scores, key=lambda s: s.overall_score, reverse=True):
        logger.info(f"    {score.speaker}: {score.overall_score:.2%}")
        logger.info(f"      supported_ratio={score.supported_ratio:.2%}, "
                    f"fallacy_count={score.fallacy_count}, "
                    f"fallacy_penalty={score.fallacy_penalty:.2%}")
        logger.info(f"      factcheck_rate={score.factcheck_positive_rate:.2%}, "
                    f"consistency={score.internal_consistency:.2%}, "
                    f"response_rate={score.direct_response_rate:.2%}")

    # Fallacy breakdown
    all_fallacies = [f for n in snapshot.nodes for f in n.fallacies]
    if all_fallacies:
        from collections import Counter
        fallacy_types = Counter(f.fallacy_type.value for f in all_fallacies)
        logger.info(f"\n  FALLACIES ({len(all_fallacies)} total):")
        for ftype, count in fallacy_types.most_common():
            logger.info(f"    {ftype}: {count}")

        logger.info("\n  TOP 5 FALLACIES (by severity):")
        top_fallacies = sorted(all_fallacies, key=lambda f: f.severity, reverse=True)[:5]
        for f in top_fallacies:
            node = next((n for n in snapshot.nodes if n.id == f.claim_id), None)
            speaker = node.speaker if node else "?"
            logger.info(f"    [{speaker}] {f.fallacy_type.value} (severity={f.severity:.2f})")
            logger.info(f"      Claim: {(node.label if node else '?')[:70]}")
            logger.info(f"      Q: {f.socratic_question[:80]}")

    # Fact-check breakdown
    factchecked = [n for n in snapshot.nodes if n.factcheck_verdict.value != "pending"]
    if factchecked:
        from collections import Counter
        verdicts = Counter(n.factcheck_verdict.value for n in factchecked)
        logger.info(f"\n  FACT-CHECKS ({len(factchecked)} total):")
        for verdict, count in verdicts.most_common():
            logger.info(f"    {verdict}: {count}")

    # Edge type breakdown
    from collections import Counter
    edge_types = Counter(e.relation_type.value for e in snapshot.edges)
    logger.info(f"\n  EDGE TYPES:")
    for etype, count in edge_types.most_common():
        logger.info(f"    {etype}: {count}")

    # Claim type breakdown
    claim_types = Counter(n.claim_type.value for n in snapshot.nodes)
    logger.info(f"\n  CLAIM TYPES:")
    for ctype, count in claim_types.most_common():
        logger.info(f"    {ctype}: {count}")

    # ── Step 5: Save JSON snapshot ─────────────────────────────────────────
    logger.info("\n[5/5] SAVING JSON SNAPSHOT...")
    snapshot_path = Path(__file__).parent.parent / "logs" / "e2e_test_snapshot.json"
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        logger.info(f"  ✓ Snapshot saved to: {snapshot_path}")
    except Exception as e:
        logger.error(f"  ✗ Failed to save JSON: {e}")

    # ── Summary ────────────────────────────────────────────────────────────
    total_time = time.time() - t_start
    logger.info("\n" + "=" * 70)
    logger.info("  PIPELINE TEST COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  Total time:        {total_time:.1f}s ({total_time/60:.1f} min)")
    logger.info(f"  Transcription:     {t_transcription:.1f}s")
    logger.info(f"  Analysis:          {t_analysis:.1f}s")
    logger.info(f"  Job ID:            {job_id}")
    logger.info(f"  Nodes:             {len(snapshot.nodes)}")
    logger.info(f"  Edges:             {len(snapshot.edges)}")
    logger.info(f"  Fallacies:         {len(all_fallacies)}")
    logger.info(f"  Fact-checks:       {len(factchecked)}")
    logger.info(f"  DB viewer:         http://localhost:8010/db")
    logger.info(f"  Snapshot detail:   http://localhost:8010/db/snapshot/{job_id}")
    logger.info("=" * 70)

    # ── DB verification ────────────────────────────────────────────────────
    if list_jobs:
        logger.info("\n  DB VERIFICATION:")
        jobs = list_jobs()
        logger.info(f"  Total jobs in DB: {len(jobs)}")
        for j in jobs[:3]:
            logger.info(f"    [{j['status']}] {j['id'][:8]}... — {j.get('audio_filename','?')} "
                        f"({j.get('num_nodes','?')} nodes, {j.get('num_fallacies','?')} fallacies)")

    return job_id, snapshot


if __name__ == "__main__":
    asyncio.run(main())
