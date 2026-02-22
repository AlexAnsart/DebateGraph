"""
DebateGraph — Comprehensive Backend Test Suite
Tests the FULL pipeline with REAL API calls using the 10-minute Obama vs Romney debate.

Tests:
1. Audio file validation & conversion
2. OpenAI transcription with speaker diarization
3. Ontological Agent: claim extraction via Claude Haiku
4. Graph construction (NetworkX)
5. Skeptic Agent: fallacy detection (structural + LLM)
6. Researcher Agent: fact-checking (Tavily + Claude)
7. Rigor score computation
8. Full pipeline orchestration
9. Graph algorithms (cycles, strawman, goalpost)
10. Snapshot generation for frontend

Run: cd backend ; python test_full_pipeline.py
"""

import os
import sys
import json
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Ensure backend is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ─── Logging Setup ──────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
TEST_SESSION = f"test_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
TEST_LOG_DIR = os.path.join(LOG_DIR, TEST_SESSION)
Path(TEST_LOG_DIR).mkdir(parents=True, exist_ok=True)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(TEST_LOG_DIR, "full_test.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("test_full_pipeline")

# ─── Test Configuration ─────────────────────────────────────
DEMO_AUDIO = os.path.join(os.path.dirname(__file__), '..', 'demos', 'obama_romney_10min.mp3')
RESULTS = {}
PASS_COUNT = 0
FAIL_COUNT = 0


def record_result(test_name: str, passed: bool, details: str = "", data: dict = None):
    """Record a test result."""
    global PASS_COUNT, FAIL_COUNT
    status = "✅ PASS" if passed else "❌ FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    
    RESULTS[test_name] = {
        "status": "PASS" if passed else "FAIL",
        "details": details,
        "data": data or {},
    }
    logger.info(f"\n{'='*60}")
    logger.info(f"TEST: {test_name} — {status}")
    if details:
        logger.info(f"  Details: {details}")
    logger.info(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# TEST 1: Environment & Dependencies
# ═══════════════════════════════════════════════════════════════

def test_01_environment():
    """Verify all API keys and dependencies are available."""
    logger.info("TEST 1: Environment & Dependencies")
    
    issues = []
    
    # Check API keys
    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    
    if not openai_key:
        issues.append("OPENAI_API_KEY not set")
    else:
        logger.info(f"  OPENAI_API_KEY: set ({len(openai_key)} chars, starts with {openai_key[:8]}...)")
    
    if not anthropic_key:
        issues.append("ANTHROPIC_API_KEY not set")
    else:
        logger.info(f"  ANTHROPIC_API_KEY: set ({len(anthropic_key)} chars)")
    
    if not tavily_key:
        issues.append("TAVILY_API_KEY not set (fact-checking will use mock)")
    else:
        logger.info(f"  TAVILY_API_KEY: set ({len(tavily_key)} chars)")
    
    # Check packages
    packages = {
        "anthropic": None,
        "openai": None,
        "fastapi": None,
        "networkx": None,
        "aiofiles": None,
        "pydantic": None,
    }
    for pkg in packages:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, '__version__', 'OK')
            packages[pkg] = ver
            logger.info(f"  {pkg}: {ver}")
        except ImportError as e:
            issues.append(f"{pkg} not installed: {e}")
    
    # Check tavily
    try:
        from tavily import TavilyClient
        logger.info("  tavily: OK")
    except ImportError:
        issues.append("tavily-python not installed")
    
    # Check demo audio file
    if os.path.exists(DEMO_AUDIO):
        size_mb = os.path.getsize(DEMO_AUDIO) / (1024 * 1024)
        logger.info(f"  Demo audio: {DEMO_AUDIO} ({size_mb:.1f} MB)")
    else:
        issues.append(f"Demo audio not found: {DEMO_AUDIO}")
    
    # Check ffmpeg
    try:
        from utils.audio import get_ffmpeg_path
        ffmpeg_path = get_ffmpeg_path()
        logger.info(f"  ffmpeg: {ffmpeg_path}")
    except Exception as e:
        issues.append(f"ffmpeg not available: {e}")
    
    passed = len([i for i in issues if "not set" not in i or "OPENAI" in i or "ANTHROPIC" in i]) == 0
    # We need at least OpenAI and Anthropic
    critical_issues = [i for i in issues if "OPENAI" in i or "ANTHROPIC" in i or "not found" in i]
    
    record_result(
        "01_environment",
        len(critical_issues) == 0,
        f"Issues: {issues}" if issues else "All dependencies OK",
        {"packages": packages, "issues": issues},
    )
    return len(critical_issues) == 0


# ═══════════════════════════════════════════════════════════════
# TEST 2: Audio File Validation
# ═══════════════════════════════════════════════════════════════

def test_02_audio_validation():
    """Validate the demo audio file."""
    logger.info("TEST 2: Audio File Validation")
    
    try:
        from utils.audio import get_audio_duration
        
        size_mb = os.path.getsize(DEMO_AUDIO) / (1024 * 1024)
        duration = get_audio_duration(DEMO_AUDIO)
        
        logger.info(f"  File: {DEMO_AUDIO}")
        logger.info(f"  Size: {size_mb:.1f} MB")
        logger.info(f"  Duration: {duration:.1f}s ({duration/60:.1f} min)")
        logger.info(f"  Under 25MB limit: {size_mb < 25}")
        
        passed = size_mb < 25 and duration > 0
        record_result(
            "02_audio_validation",
            passed,
            f"Size={size_mb:.1f}MB, Duration={duration:.1f}s",
            {"size_mb": size_mb, "duration_s": duration},
        )
        return passed
    except Exception as e:
        record_result("02_audio_validation", False, f"Error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# TEST 3: OpenAI Transcription with Diarization
# ═══════════════════════════════════════════════════════════════

def test_03_transcription():
    """Test OpenAI transcription with speaker diarization."""
    logger.info("TEST 3: OpenAI Transcription with Diarization")
    
    try:
        from pipeline.transcription import transcribe_audio
        
        t0 = time.time()
        result = transcribe_audio(DEMO_AUDIO)
        elapsed = time.time() - t0
        
        logger.info(f"  Transcription time: {elapsed:.1f}s")
        logger.info(f"  Segments: {len(result.segments)}")
        logger.info(f"  Speakers: {result.num_speakers}")
        logger.info(f"  Language: {result.language}")
        
        # Log all segments
        logger.info(f"\n  {'='*50}")
        logger.info(f"  FULL TRANSCRIPTION ({len(result.segments)} segments):")
        logger.info(f"  {'='*50}")
        
        speakers_seen = set()
        total_text_length = 0
        for i, seg in enumerate(result.segments):
            speakers_seen.add(seg.speaker)
            total_text_length += len(seg.text)
            logger.info(f"  [{i:3d}] [{seg.start:7.1f}s - {seg.end:7.1f}s] {seg.speaker}: {seg.text}")
        
        logger.info(f"\n  Unique speakers: {speakers_seen}")
        logger.info(f"  Total text length: {total_text_length} chars")
        logger.info(f"  Avg segment length: {total_text_length / max(len(result.segments), 1):.0f} chars")
        
        # Validation checks
        checks = {
            "has_segments": len(result.segments) > 0,
            "multiple_speakers": result.num_speakers >= 2,
            "has_timestamps": all(seg.end > seg.start or seg.end == 0 for seg in result.segments),
            "has_text": all(len(seg.text.strip()) > 0 for seg in result.segments),
            "reasonable_segment_count": 5 <= len(result.segments) <= 500,
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "03_transcription",
            all_passed,
            f"{len(result.segments)} segments, {result.num_speakers} speakers, {elapsed:.1f}s",
            {
                "segments": len(result.segments),
                "speakers": result.num_speakers,
                "language": result.language,
                "elapsed_s": elapsed,
                "checks": checks,
                "speakers_seen": list(speakers_seen),
            },
        )
        
        # Save transcription for subsequent tests
        return result if all_passed else None
        
    except Exception as e:
        logger.error(f"  Transcription failed: {e}", exc_info=True)
        record_result("03_transcription", False, f"Error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# TEST 4: Ontological Agent — Claim Extraction
# ═══════════════════════════════════════════════════════════════

async def test_04_claim_extraction(transcription):
    """Test claim extraction using Claude Haiku."""
    logger.info("TEST 4: Ontological Agent — Claim Extraction")
    
    if transcription is None:
        record_result("04_claim_extraction", False, "Skipped: no transcription available")
        return None
    
    try:
        from agents.ontological import OntologicalAgent
        from graph.store import DebateGraphStore
        
        graph_store = DebateGraphStore()
        agent = OntologicalAgent()
        
        t0 = time.time()
        await agent.extract_and_build(transcription, graph_store)
        elapsed = time.time() - t0
        
        claims = graph_store.get_all_claims()
        relations = graph_store.get_relations()
        speakers = graph_store.get_speakers()
        
        logger.info(f"  Extraction time: {elapsed:.1f}s")
        logger.info(f"  Claims extracted: {len(claims)}")
        logger.info(f"  Relations found: {len(relations)}")
        logger.info(f"  Speakers: {speakers}")
        
        # Log all claims
        logger.info(f"\n  {'='*50}")
        logger.info(f"  ALL CLAIMS ({len(claims)}):")
        logger.info(f"  {'='*50}")
        
        claim_types = {}
        factual_count = 0
        for claim in claims:
            ct = claim.claim_type.value
            claim_types[ct] = claim_types.get(ct, 0) + 1
            if claim.is_factual:
                factual_count += 1
            logger.info(
                f"  [{claim.id}] {claim.speaker} | {ct:12s} | "
                f"{'FACTUAL' if claim.is_factual else 'OPINION':8s} | "
                f"[{claim.timestamp_start:.1f}s-{claim.timestamp_end:.1f}s] | "
                f"{claim.text}"
            )
        
        logger.info(f"\n  Claim type distribution: {claim_types}")
        logger.info(f"  Factual claims: {factual_count}/{len(claims)}")
        
        # Log all relations
        logger.info(f"\n  {'='*50}")
        logger.info(f"  ALL RELATIONS ({len(relations)}):")
        logger.info(f"  {'='*50}")
        
        relation_types = {}
        for rel in relations:
            rt = rel.relation_type.value
            relation_types[rt] = relation_types.get(rt, 0) + 1
            src_claim = graph_store.get_claim(rel.source_id)
            tgt_claim = graph_store.get_claim(rel.target_id)
            src_text = src_claim.text[:50] if src_claim else "?"
            tgt_text = tgt_claim.text[:50] if tgt_claim else "?"
            logger.info(
                f"  {rel.source_id} --[{rt}]--> {rel.target_id} "
                f"(conf={rel.confidence:.2f})"
            )
            logger.info(f"    SRC: {src_text}...")
            logger.info(f"    TGT: {tgt_text}...")
        
        logger.info(f"\n  Relation type distribution: {relation_types}")
        
        # Validation checks
        checks = {
            "has_claims": len(claims) >= 3,
            "has_relations": len(relations) >= 1,
            "multiple_speakers_in_claims": len(speakers) >= 2,
            "has_claim_types": len(claim_types) >= 2,
            "has_factual_claims": factual_count > 0,
            "claims_have_text": all(len(c.text.strip()) > 0 for c in claims),
            "claims_have_timestamps": all(c.timestamp_end >= c.timestamp_start for c in claims),
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "04_claim_extraction",
            all_passed,
            f"{len(claims)} claims, {len(relations)} relations, {elapsed:.1f}s",
            {
                "claims": len(claims),
                "relations": len(relations),
                "speakers": speakers,
                "claim_types": claim_types,
                "relation_types": relation_types,
                "factual_count": factual_count,
                "elapsed_s": elapsed,
                "checks": checks,
            },
        )
        
        return graph_store if all_passed else graph_store  # Return even if not all pass
        
    except Exception as e:
        logger.error(f"  Claim extraction failed: {e}", exc_info=True)
        record_result("04_claim_extraction", False, f"Error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# TEST 5: Graph Structure Validation
# ═══════════════════════════════════════════════════════════════

def test_05_graph_structure(graph_store):
    """Test the NetworkX graph structure."""
    logger.info("TEST 5: Graph Structure Validation")
    
    if graph_store is None:
        record_result("05_graph_structure", False, "Skipped: no graph store available")
        return
    
    try:
        from graph.algorithms import compute_graph_stats, detect_cycles
        
        stats = compute_graph_stats(graph_store.graph)
        
        logger.info(f"  Graph stats:")
        for key, value in stats.items():
            logger.info(f"    {key}: {value}")
        
        # Check graph properties
        import networkx as nx
        
        num_nodes = graph_store.graph.number_of_nodes()
        num_edges = graph_store.graph.number_of_edges()
        
        # Connected components (undirected)
        undirected = graph_store.graph.to_undirected()
        components = list(nx.connected_components(undirected))
        logger.info(f"  Connected components: {len(components)}")
        for i, comp in enumerate(components):
            logger.info(f"    Component {i}: {len(comp)} nodes")
        
        # Degree distribution
        in_degrees = dict(graph_store.graph.in_degree())
        out_degrees = dict(graph_store.graph.out_degree())
        logger.info(f"  Max in-degree: {max(in_degrees.values()) if in_degrees else 0}")
        logger.info(f"  Max out-degree: {max(out_degrees.values()) if out_degrees else 0}")
        logger.info(f"  Isolated nodes: {sum(1 for d in in_degrees.values() if d == 0) + sum(1 for d in out_degrees.values() if d == 0)}")
        
        # Density
        density = nx.density(graph_store.graph)
        logger.info(f"  Graph density: {density:.4f}")
        
        checks = {
            "has_nodes": num_nodes > 0,
            "has_edges": num_edges > 0,
            "reasonable_density": 0.001 <= density <= 0.9,
            "not_too_fragmented": len(components) <= num_nodes * 0.8,
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "05_graph_structure",
            all_passed,
            f"{num_nodes} nodes, {num_edges} edges, {len(components)} components, density={density:.4f}",
            {"stats": stats, "checks": checks},
        )
        
    except Exception as e:
        logger.error(f"  Graph structure test failed: {e}", exc_info=True)
        record_result("05_graph_structure", False, f"Error: {e}")


# ═══════════════════════════════════════════════════════════════
# TEST 6: Skeptic Agent — Fallacy Detection
# ═══════════════════════════════════════════════════════════════

async def test_06_fallacy_detection(graph_store):
    """Test fallacy detection using structural + LLM analysis."""
    logger.info("TEST 6: Skeptic Agent — Fallacy Detection")
    
    if graph_store is None:
        record_result("06_fallacy_detection", False, "Skipped: no graph store available")
        return
    
    try:
        from agents.skeptic import SkepticAgent
        
        agent = SkepticAgent()
        
        t0 = time.time()
        fallacies = await agent.analyze(graph_store)
        elapsed = time.time() - t0
        
        logger.info(f"  Detection time: {elapsed:.1f}s")
        logger.info(f"  Fallacies detected: {len(fallacies)}")
        
        # Log all fallacies
        logger.info(f"\n  {'='*50}")
        logger.info(f"  ALL FALLACIES ({len(fallacies)}):")
        logger.info(f"  {'='*50}")
        
        fallacy_types = {}
        for f in fallacies:
            ft = f.fallacy_type.value
            fallacy_types[ft] = fallacy_types.get(ft, 0) + 1
            claim = graph_store.get_claim(f.claim_id)
            claim_text = claim.text[:60] if claim else "?"
            logger.info(
                f"  [{f.claim_id}] {ft} (severity={f.severity:.2f})"
            )
            logger.info(f"    Claim: {claim_text}...")
            logger.info(f"    Explanation: {f.explanation}")
            logger.info(f"    Socratic Q: {f.socratic_question}")
            if f.related_claim_ids:
                logger.info(f"    Related: {f.related_claim_ids}")
        
        logger.info(f"\n  Fallacy type distribution: {fallacy_types}")
        
        # The test passes if the agent ran without errors
        # (it's OK if no fallacies are found in a real debate)
        checks = {
            "agent_ran_successfully": True,
            "fallacies_have_valid_types": all(
                f.fallacy_type.value in [ft.value for ft in __import__('api.models.schemas', fromlist=['FallacyType']).FallacyType]
                for f in fallacies
            ),
            "fallacies_have_explanations": all(len(f.explanation) > 0 for f in fallacies) if fallacies else True,
            "severity_in_range": all(0.0 <= f.severity <= 1.0 for f in fallacies) if fallacies else True,
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "06_fallacy_detection",
            all_passed,
            f"{len(fallacies)} fallacies detected in {elapsed:.1f}s",
            {
                "fallacies_count": len(fallacies),
                "fallacy_types": fallacy_types,
                "elapsed_s": elapsed,
                "checks": checks,
            },
        )
        
    except Exception as e:
        logger.error(f"  Fallacy detection failed: {e}", exc_info=True)
        record_result("06_fallacy_detection", False, f"Error: {e}")


# ═══════════════════════════════════════════════════════════════
# TEST 7: Researcher Agent — Fact-Checking
# ═══════════════════════════════════════════════════════════════

async def test_07_fact_checking(graph_store):
    """Test fact-checking using Tavily + Claude."""
    logger.info("TEST 7: Researcher Agent — Fact-Checking")
    
    if graph_store is None:
        record_result("07_fact_checking", False, "Skipped: no graph store available")
        return
    
    try:
        from agents.researcher import ResearcherAgent
        
        agent = ResearcherAgent()
        
        # List factual claims first
        claims = graph_store.get_all_claims()
        factual_claims = [c for c in claims if c.is_factual]
        logger.info(f"  Total claims: {len(claims)}")
        logger.info(f"  Factual claims to check: {len(factual_claims)}")
        
        for fc in factual_claims:
            logger.info(f"    [{fc.id}] {fc.speaker}: {fc.text[:80]}...")
        
        t0 = time.time()
        results = await agent.check_all_factual_claims(graph_store)
        elapsed = time.time() - t0
        
        logger.info(f"\n  Fact-check time: {elapsed:.1f}s")
        logger.info(f"  Results: {len(results)}")
        
        # Log all results
        logger.info(f"\n  {'='*50}")
        logger.info(f"  FACT-CHECK RESULTS ({len(results)}):")
        logger.info(f"  {'='*50}")
        
        verdicts = {}
        for r in results:
            v = r.verdict.value
            verdicts[v] = verdicts.get(v, 0) + 1
            claim = graph_store.get_claim(r.claim_id)
            claim_text = claim.text[:60] if claim else "?"
            logger.info(
                f"  [{r.claim_id}] {v} (confidence={r.confidence:.2f})"
            )
            logger.info(f"    Claim: {claim_text}...")
            logger.info(f"    Explanation: {r.explanation[:200]}")
            if r.sources:
                logger.info(f"    Sources: {r.sources[:3]}")
        
        logger.info(f"\n  Verdict distribution: {verdicts}")
        
        checks = {
            "agent_ran_successfully": True,
            "results_match_factual_claims": len(results) == len(factual_claims),
            "verdicts_are_valid": all(
                r.verdict.value in ["supported", "refuted", "partially_true", "unverifiable", "pending"]
                for r in results
            ),
            "confidence_in_range": all(0.0 <= r.confidence <= 1.0 for r in results),
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "07_fact_checking",
            all_passed,
            f"{len(results)} claims checked, verdicts: {verdicts}, {elapsed:.1f}s",
            {
                "results_count": len(results),
                "verdicts": verdicts,
                "elapsed_s": elapsed,
                "checks": checks,
            },
        )
        
    except Exception as e:
        logger.error(f"  Fact-checking failed: {e}", exc_info=True)
        record_result("07_fact_checking", False, f"Error: {e}")


# ═══════════════════════════════════════════════════════════════
# TEST 8: Graph Algorithms
# ═══════════════════════════════════════════════════════════════

def test_08_graph_algorithms(graph_store):
    """Test graph algorithms: cycles, strawman, goalpost, drift."""
    logger.info("TEST 8: Graph Algorithms")
    
    if graph_store is None:
        record_result("08_graph_algorithms", False, "Skipped: no graph store available")
        return
    
    try:
        from graph.algorithms import (
            detect_cycles,
            detect_strawman_candidates,
            detect_goalpost_moving,
            detect_topic_drift,
            compute_graph_stats,
        )
        
        # Cycles
        cycles = detect_cycles(graph_store.graph)
        logger.info(f"  Cycles detected: {len(cycles)}")
        for i, cycle in enumerate(cycles):
            logger.info(f"    Cycle {i}: {' → '.join(cycle)}")
        
        # Strawman candidates
        strawman = detect_strawman_candidates(graph_store.graph)
        logger.info(f"  Strawman candidates: {len(strawman)}")
        for s in strawman:
            logger.info(f"    {s['attacker']} attacks {s['original_speaker']}: "
                       f"'{s['attacking_text'][:50]}...' vs '{s['original_text'][:50]}...'")
        
        # Goalpost moving
        goalpost = detect_goalpost_moving(graph_store.graph)
        logger.info(f"  Goalpost shifts: {len(goalpost)}")
        for g in goalpost:
            logger.info(f"    {g['speaker']}: '{g['original_text'][:50]}...'")
        
        # Topic drift
        drift = detect_topic_drift(graph_store.graph)
        logger.info(f"  Topic drifts: {len(drift)}")
        for d in drift:
            logger.info(f"    At {d['timestamp']:.1f}s, connectivity={d['connectivity_to_original']}")
        
        # Graph stats
        stats = compute_graph_stats(graph_store.graph)
        logger.info(f"  Graph stats: {json.dumps(stats, indent=2)}")
        
        checks = {
            "algorithms_ran_successfully": True,
            "stats_computed": len(stats) > 0,
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "08_graph_algorithms",
            all_passed,
            f"Cycles={len(cycles)}, Strawman={len(strawman)}, Goalpost={len(goalpost)}, Drift={len(drift)}",
            {
                "cycles": len(cycles),
                "strawman_candidates": len(strawman),
                "goalpost_shifts": len(goalpost),
                "topic_drifts": len(drift),
                "stats": stats,
                "checks": checks,
            },
        )
        
    except Exception as e:
        logger.error(f"  Graph algorithms failed: {e}", exc_info=True)
        record_result("08_graph_algorithms", False, f"Error: {e}")


# ═══════════════════════════════════════════════════════════════
# TEST 9: Rigor Scores
# ═══════════════════════════════════════════════════════════════

def test_09_rigor_scores(graph_store):
    """Test rigor score computation."""
    logger.info("TEST 9: Rigor Score Computation")
    
    if graph_store is None:
        record_result("09_rigor_scores", False, "Skipped: no graph store available")
        return
    
    try:
        scores = graph_store.compute_rigor_scores()
        
        logger.info(f"  Rigor scores computed for {len(scores)} speakers:")
        
        for score in scores:
            logger.info(f"\n  Speaker: {score.speaker}")
            logger.info(f"    Overall score:        {score.overall_score:.3f}")
            logger.info(f"    Supported ratio:      {score.supported_ratio:.3f}")
            logger.info(f"    Fallacy count:        {score.fallacy_count}")
            logger.info(f"    Fallacy penalty:      {score.fallacy_penalty:.3f}")
            logger.info(f"    Factcheck pos. rate:  {score.factcheck_positive_rate:.3f}")
            logger.info(f"    Internal consistency: {score.internal_consistency:.3f}")
            logger.info(f"    Direct response rate: {score.direct_response_rate:.3f}")
        
        checks = {
            "has_scores": len(scores) > 0,
            "scores_in_range": all(0.0 <= s.overall_score <= 1.0 for s in scores),
            "multiple_speakers_scored": len(scores) >= 2,
            "consistency_in_range": all(0.0 <= s.internal_consistency <= 1.0 for s in scores),
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "09_rigor_scores",
            all_passed,
            f"{len(scores)} speakers scored",
            {
                "scores": [
                    {
                        "speaker": s.speaker,
                        "overall": s.overall_score,
                        "supported_ratio": s.supported_ratio,
                        "fallacy_count": s.fallacy_count,
                        "factcheck_rate": s.factcheck_positive_rate,
                    }
                    for s in scores
                ],
                "checks": checks,
            },
        )
        
    except Exception as e:
        logger.error(f"  Rigor scores failed: {e}", exc_info=True)
        record_result("09_rigor_scores", False, f"Error: {e}")


# ═══════════════════════════════════════════════════════════════
# TEST 10: Snapshot Generation
# ═══════════════════════════════════════════════════════════════

def test_10_snapshot(graph_store):
    """Test snapshot generation for frontend."""
    logger.info("TEST 10: Snapshot Generation")
    
    if graph_store is None:
        record_result("10_snapshot", False, "Skipped: no graph store available")
        return
    
    try:
        snapshot = graph_store.to_snapshot()
        
        logger.info(f"  Snapshot nodes: {len(snapshot.nodes)}")
        logger.info(f"  Snapshot edges: {len(snapshot.edges)}")
        logger.info(f"  Rigor scores: {len(snapshot.rigor_scores)}")
        logger.info(f"  Cycles detected: {len(snapshot.cycles_detected)}")
        
        # Verify JSON serialization
        snapshot_dict = snapshot.model_dump(mode="json")
        snapshot_json = json.dumps(snapshot_dict, indent=2)
        
        logger.info(f"  JSON size: {len(snapshot_json)} chars")
        
        # Save snapshot to file
        snapshot_path = os.path.join(TEST_LOG_DIR, "snapshot.json")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(snapshot_json)
        logger.info(f"  Snapshot saved to: {snapshot_path}")
        
        # Also save to logs root for the /api/snapshot/latest endpoint
        root_snapshot_path = os.path.join(LOG_DIR, "e2e_test_snapshot.json")
        with open(root_snapshot_path, "w", encoding="utf-8") as f:
            f.write(snapshot_json)
        logger.info(f"  Snapshot also saved to: {root_snapshot_path}")
        
        # Log some node details
        logger.info(f"\n  Sample nodes:")
        for node in snapshot.nodes[:5]:
            logger.info(f"    [{node.id}] {node.speaker} | {node.claim_type.value} | "
                       f"factcheck={node.factcheck_verdict.value} | "
                       f"fallacies={len(node.fallacies)} | "
                       f"{node.label}")
        
        # Log some edge details
        logger.info(f"\n  Sample edges:")
        for edge in snapshot.edges[:5]:
            logger.info(f"    {edge.source} --[{edge.relation_type.value}]--> {edge.target} "
                       f"(conf={edge.confidence:.2f})")
        
        checks = {
            "has_nodes": len(snapshot.nodes) > 0,
            "has_edges": len(snapshot.edges) > 0,
            "json_serializable": len(snapshot_json) > 0,
            "nodes_have_required_fields": all(
                n.id and n.speaker and n.label for n in snapshot.nodes
            ),
            "edges_reference_valid_nodes": all(
                any(n.id == e.source for n in snapshot.nodes) and
                any(n.id == e.target for n in snapshot.nodes)
                for e in snapshot.edges
            ),
        }
        
        for check, passed in checks.items():
            logger.info(f"  Check {check}: {'✅' if passed else '❌'}")
        
        all_passed = all(checks.values())
        record_result(
            "10_snapshot",
            all_passed,
            f"{len(snapshot.nodes)} nodes, {len(snapshot.edges)} edges, JSON={len(snapshot_json)} chars",
            {
                "nodes": len(snapshot.nodes),
                "edges": len(snapshot.edges),
                "json_size": len(snapshot_json),
                "checks": checks,
            },
        )
        
    except Exception as e:
        logger.error(f"  Snapshot generation failed: {e}", exc_info=True)
        record_result("10_snapshot", False, f"Error: {e}")


# ═══════════════════════════════════════════════════════════════
# MAIN — Run All Tests
# ═══════════════════════════════════════════════════════════════

async def run_all_tests():
    """Run the complete test suite."""
    total_start = time.time()
    
    logger.info("╔" + "═"*58 + "╗")
    logger.info("║  DebateGraph — Comprehensive Backend Test Suite           ║")
    logger.info("║  Using REAL API calls (OpenAI + Claude Haiku + Tavily)    ║")
    logger.info("║  Audio: Obama vs Romney 10-min debate                     ║")
    logger.info("╚" + "═"*58 + "╝")
    logger.info(f"  Log directory: {TEST_LOG_DIR}")
    logger.info("")
    
    # Test 1: Environment
    env_ok = test_01_environment()
    if not env_ok:
        logger.error("CRITICAL: Environment check failed. Cannot proceed.")
        return
    
    # Test 2: Audio validation
    test_02_audio_validation()
    
    # Test 3: Transcription (REAL OpenAI API call)
    transcription = test_03_transcription()
    
    # Save transcription to file for debugging
    if transcription:
        trans_path = os.path.join(TEST_LOG_DIR, "transcription.json")
        with open(trans_path, "w", encoding="utf-8") as f:
            json.dump(transcription.model_dump(mode="json"), f, indent=2)
        logger.info(f"  Transcription saved to: {trans_path}")
    
    # Test 4: Claim extraction (REAL Claude Haiku API call)
    graph_store = await test_04_claim_extraction(transcription)
    
    # Test 5: Graph structure
    test_05_graph_structure(graph_store)
    
    # Test 6: Fallacy detection (REAL Claude Haiku API call)
    await test_06_fallacy_detection(graph_store)
    
    # Test 7: Fact-checking (REAL Tavily + Claude API calls)
    await test_07_fact_checking(graph_store)
    
    # Test 8: Graph algorithms
    test_08_graph_algorithms(graph_store)
    
    # Test 9: Rigor scores
    test_09_rigor_scores(graph_store)
    
    # Test 10: Snapshot generation
    test_10_snapshot(graph_store)
    
    # ─── Summary ────────────────────────────────────────────
    total_time = time.time() - total_start
    
    logger.info("\n" + "═"*60)
    logger.info("TEST SUITE SUMMARY")
    logger.info("═"*60)
    logger.info(f"  Total tests: {PASS_COUNT + FAIL_COUNT}")
    logger.info(f"  Passed:      {PASS_COUNT} ✅")
    logger.info(f"  Failed:      {FAIL_COUNT} ❌")
    logger.info(f"  Total time:  {total_time:.1f}s ({total_time/60:.1f} min)")
    logger.info(f"  Log dir:     {TEST_LOG_DIR}")
    logger.info("═"*60)
    
    for test_name, result in RESULTS.items():
        status = "✅" if result["status"] == "PASS" else "❌"
        logger.info(f"  {status} {test_name}: {result['details'][:80]}")
    
    logger.info("═"*60)
    
    # Save results summary
    summary_path = os.path.join(TEST_LOG_DIR, "results_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_tests": PASS_COUNT + FAIL_COUNT,
            "passed": PASS_COUNT,
            "failed": FAIL_COUNT,
            "total_time_s": total_time,
            "results": RESULTS,
        }, f, indent=2, default=str)
    logger.info(f"  Results saved to: {summary_path}")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
