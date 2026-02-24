"""
Central Orchestrator — Intent Router
Coordinates the multi-agent analysis pipeline with structured logging.

Pipeline flow:
1. Ontological Agent: Extract claims + build graph
2. Skeptic Agent: Detect fallacies
3. Researcher Agent: Fact-check factual claims (parallel)
4. Compute rigor scores
5. Return graph snapshot
"""

import time
import logging

from api.models.schemas import (
    TranscriptionResult,
    GraphSnapshot,
)
from graph.store import DebateGraphStore
from agents.ontological import OntologicalAgent
from agents.skeptic import SkepticAgent
from agents.researcher import ResearcherAgent
from config.logging_config import setup_session_logging
from session_log.session_structured_logger import SessionLogger

logger = logging.getLogger("debategraph")


async def run_analysis_pipeline(
    transcription: TranscriptionResult,
    graph_store: DebateGraphStore,
    session_id: str = None,
) -> GraphSnapshot:
    """
    Run the full multi-agent analysis pipeline on a transcription.

    Args:
        transcription: Speaker-attributed transcription result
        graph_store: Empty graph store to populate
        session_id: Optional session ID for logging

    Returns:
        GraphSnapshot ready for frontend rendering
    """
    # Set up session logging (text logs + structured JSONL)
    session_dir = setup_session_logging(session_id)
    session_logger = SessionLogger(session_dir)

    pipeline_start = time.time()

    logger.info("=" * 60)
    logger.info("STARTING ANALYSIS PIPELINE")
    logger.info(f"Session: {session_dir}")
    logger.info(f"Segments: {len(transcription.segments)}, "
                f"Speakers: {transcription.num_speakers}, "
                f"Language: {transcription.language}")
    logger.info("=" * 60)

    # ─── Step 1: Ontological Agent — Claim Extraction & Graph Building ───
    t0 = time.time()
    logger.info("[Step 1/4] Ontological Agent: Extracting claims...")
    ontological = OntologicalAgent(session_logger=session_logger)
    await ontological.extract_and_build(transcription, graph_store)
    t1 = time.time()
    logger.info(f"  → Graph: {graph_store.num_nodes} nodes, {graph_store.num_edges} edges "
                f"({t1 - t0:.1f}s)")

    # ─── Step 2: Skeptic Agent — Fallacy Detection ──────────────────────
    logger.info("[Step 2/4] Skeptic Agent: Detecting fallacies...")
    skeptic = SkepticAgent(session_logger=session_logger)
    fallacies = await skeptic.analyze(graph_store)
    t2 = time.time()
    logger.info(f"  → Detected {len(fallacies)} fallacies ({t2 - t1:.1f}s)")

    # ─── Step 3: Researcher Agent — Fact-Checking ───────────────────────
    logger.info("[Step 3/4] Researcher Agent: Fact-checking claims...")
    researcher = ResearcherAgent(session_logger=session_logger)
    factchecks = await researcher.check_all_factual_claims(graph_store)
    t3 = time.time()
    logger.info(f"  → Fact-checked {len(factchecks)} claims ({t3 - t2:.1f}s)")

    # ─── Step 4: Compute Rigor Scores ───────────────────────────────────
    logger.info("[Step 4/4] Computing rigor scores...")
    rigor_scores = graph_store.compute_rigor_scores()
    for score in rigor_scores:
        logger.info(f"  → {score.speaker}: {score.overall_score:.2f} "
                     f"(fallacy_penalty={score.fallacy_penalty:.2f}, "
                     f"supported_ratio={score.supported_ratio:.2f}, "
                     f"factcheck_rate={score.factcheck_positive_rate:.2f})")

    # ─── Generate Snapshot ──────────────────────────────────────────────
    snapshot = graph_store.to_snapshot()

    total_time = time.time() - pipeline_start
    
    logger.info("=" * 60)
    logger.info("ANALYSIS PIPELINE COMPLETE")
    logger.info(f"Total time: {total_time:.1f}s")
    logger.info(f"Nodes: {len(snapshot.nodes)}, Edges: {len(snapshot.edges)}, "
                f"Fallacies: {sum(len(n.fallacies) for n in snapshot.nodes)}, "
                f"Fact-checks: {len([n for n in snapshot.nodes if n.factcheck])}, "
                f"Cycles: {len(snapshot.cycles_detected)}")
    session_logger.set_ended_at()
    logger.info(f"Logs saved to: {session_dir}")
    logger.info("=" * 60)

    return snapshot
