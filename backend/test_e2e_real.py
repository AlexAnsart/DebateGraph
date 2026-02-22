"""
End-to-end test of the DebateGraph pipeline with REAL audio and REAL API calls.
Tests: OpenAI transcription → Claude claim extraction → fallacy detection → fact-checking

Usage:
    cd backend
    python test_e2e_real.py
"""

import os
import sys
import json
import time
import asyncio
import logging
from pathlib import Path

# Ensure we can import from the backend package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_e2e")


def check_prerequisites():
    """Verify all API keys and dependencies are available."""
    print("=" * 70)
    print("  DebateGraph — End-to-End Real Pipeline Test")
    print("=" * 70)
    
    issues = []
    
    # Check OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        issues.append("OPENAI_API_KEY not set in .env")
    else:
        print(f"  ✓ OPENAI_API_KEY: ...{openai_key[-8:]}")
    
    # Check Anthropic
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        issues.append("ANTHROPIC_API_KEY not set in .env")
    else:
        print(f"  ✓ ANTHROPIC_API_KEY: ...{anthropic_key[-8:]}")
    
    # Check Tavily (optional)
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_key:
        print(f"  ✓ TAVILY_API_KEY: ...{tavily_key[-8:]}")
    else:
        print(f"  ⚠ TAVILY_API_KEY not set (fact-checking will use mock)")
    
    # Check audio file
    audio_path = os.path.join(os.path.dirname(__file__), '..', 'demos', 'obama_romney_10min.mp3')
    if not os.path.exists(audio_path):
        issues.append(f"Audio file not found: {audio_path}")
    else:
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"  ✓ Audio file: obama_romney_10min.mp3 ({size_mb:.1f} MB)")
    
    # Check packages
    try:
        import openai
        print(f"  ✓ openai: {openai.__version__}")
    except ImportError:
        issues.append("openai package not installed")
    
    try:
        import anthropic
        print(f"  ✓ anthropic: {anthropic.__version__}")
    except ImportError:
        issues.append("anthropic package not installed")
    
    print()
    
    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  ✗ {issue}")
        print()
        return False
    
    return True


def test_transcription(audio_path: str):
    """Test OpenAI transcription with real audio."""
    print("=" * 70)
    print("  STEP 1: OpenAI Transcription (gpt-4o-transcribe)")
    print("=" * 70)
    
    from pipeline.transcription import transcribe_audio
    
    t0 = time.time()
    result = transcribe_audio(audio_path)
    elapsed = time.time() - t0
    
    print(f"\n  Transcription completed in {elapsed:.1f}s")
    print(f"  Segments: {len(result.segments)}")
    print(f"  Speakers: {result.num_speakers}")
    print(f"  Language: {result.language}")
    
    # Analyze segments
    speakers = {}
    total_words = 0
    for seg in result.segments:
        if seg.speaker not in speakers:
            speakers[seg.speaker] = {"count": 0, "words": 0, "total_duration": 0.0}
        speakers[seg.speaker]["count"] += 1
        words = len(seg.text.split())
        speakers[seg.speaker]["words"] += words
        speakers[seg.speaker]["total_duration"] += (seg.end - seg.start)
        total_words += words
    
    print(f"  Total words: {total_words}")
    print(f"\n  Speaker breakdown:")
    for spk, stats in sorted(speakers.items()):
        print(f"    {spk}: {stats['count']} segments, {stats['words']} words, "
              f"{stats['total_duration']:.1f}s speaking time")
    
    # Show first 10 segments
    print(f"\n  First 10 segments:")
    for i, seg in enumerate(result.segments[:10]):
        text_preview = seg.text[:100] + ("..." if len(seg.text) > 100 else "")
        print(f"    [{seg.start:.1f}s-{seg.end:.1f}s] {seg.speaker}: {text_preview}")
    
    # Check for very long segments (potential issue for LLM processing)
    long_segments = [s for s in result.segments if len(s.text.split()) > 100]
    if long_segments:
        print(f"\n  ⚠ WARNING: {len(long_segments)} segments have >100 words")
        print(f"    These may need to be split for better claim extraction")
        for seg in long_segments[:3]:
            print(f"    - {seg.speaker} [{seg.start:.1f}s-{seg.end:.1f}s]: "
                  f"{len(seg.text.split())} words")
    
    print()
    return result


async def test_full_pipeline(transcription):
    """Test the full analysis pipeline with real transcription."""
    print("=" * 70)
    print("  STEP 2: Full Analysis Pipeline")
    print("=" * 70)
    
    from agents.orchestrator import run_analysis_pipeline
    from graph.store import DebateGraphStore
    
    graph_store = DebateGraphStore()
    
    t0 = time.time()
    snapshot = await run_analysis_pipeline(
        transcription, graph_store, session_id="e2e_test"
    )
    elapsed = time.time() - t0
    
    print(f"\n  Pipeline completed in {elapsed:.1f}s")
    print(f"  Nodes: {len(snapshot.nodes)}")
    print(f"  Edges: {len(snapshot.edges)}")
    print(f"  Cycles: {len(snapshot.cycles_detected)}")
    
    # Claims analysis
    print(f"\n  ─── Claims ───")
    claims_by_speaker = {}
    claims_by_type = {}
    factual_claims = []
    
    for node in snapshot.nodes:
        if node.speaker not in claims_by_speaker:
            claims_by_speaker[node.speaker] = []
        claims_by_speaker[node.speaker].append(node)
        
        ct = node.claim_type.value
        claims_by_type[ct] = claims_by_type.get(ct, 0) + 1
        
        if node.is_factual:
            factual_claims.append(node)
    
    for spk, claims in sorted(claims_by_speaker.items()):
        print(f"    {spk}: {len(claims)} claims")
    
    print(f"    Claim types: {claims_by_type}")
    print(f"    Factual claims: {len(factual_claims)}")
    
    # Show some claims
    print(f"\n  Sample claims:")
    for node in snapshot.nodes[:8]:
        print(f"    [{node.id}] {node.speaker} ({node.claim_type.value}): "
              f"{node.label}")
    
    # Edge analysis
    print(f"\n  ─── Relations ───")
    edge_types = {}
    for edge in snapshot.edges:
        et = edge.relation_type.value
        edge_types[et] = edge_types.get(et, 0) + 1
    print(f"    Edge types: {edge_types}")
    
    # Fallacy analysis
    print(f"\n  ─── Fallacies ───")
    all_fallacies = []
    for node in snapshot.nodes:
        for f in node.fallacies:
            all_fallacies.append((node, f))
    
    if all_fallacies:
        fallacy_types = {}
        for node, f in all_fallacies:
            ft = f.fallacy_type.value
            fallacy_types[ft] = fallacy_types.get(ft, 0) + 1
        
        print(f"    Total fallacies: {len(all_fallacies)}")
        print(f"    Types: {fallacy_types}")
        
        for node, f in all_fallacies[:5]:
            print(f"    [{node.id}] {f.fallacy_type.value} (severity={f.severity:.2f})")
            print(f"      Explanation: {f.explanation[:120]}...")
            if f.socratic_question:
                print(f"      Socratic Q: {f.socratic_question[:120]}...")
    else:
        print(f"    No fallacies detected")
    
    # Fact-check analysis
    print(f"\n  ─── Fact-Checks ───")
    factchecked = [n for n in snapshot.nodes if n.factcheck]
    if factchecked:
        verdicts = {}
        for n in factchecked:
            v = n.factcheck.verdict.value
            verdicts[v] = verdicts.get(v, 0) + 1
        
        print(f"    Fact-checked claims: {len(factchecked)}")
        print(f"    Verdicts: {verdicts}")
        
        for n in factchecked[:5]:
            fc = n.factcheck
            print(f"    [{n.id}] {fc.verdict.value} (confidence={fc.confidence:.2f})")
            print(f"      Claim: {n.label}")
            print(f"      Explanation: {fc.explanation[:150]}...")
            if fc.sources:
                print(f"      Sources: {fc.sources[:2]}")
    else:
        print(f"    No fact-checks performed")
    
    # Rigor scores
    print(f"\n  ─── Rigor Scores ───")
    for score in snapshot.rigor_scores:
        print(f"    {score.speaker}: {score.overall_score:.3f}")
        print(f"      Supported ratio: {score.supported_ratio:.3f}")
        print(f"      Fallacy count: {score.fallacy_count} (penalty: {score.fallacy_penalty:.3f})")
        print(f"      Fact-check rate: {score.factcheck_positive_rate:.3f}")
        print(f"      Consistency: {score.internal_consistency:.3f}")
        print(f"      Response rate: {score.direct_response_rate:.3f}")
    
    # Save full snapshot to JSON for inspection
    output_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'e2e_test_snapshot.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    print(f"\n  Full snapshot saved to: {output_path}")
    
    print()
    return snapshot


def main():
    if not check_prerequisites():
        print("Fix the issues above and try again.")
        sys.exit(1)
    
    audio_path = os.path.join(os.path.dirname(__file__), '..', 'demos', 'obama_romney_10min.mp3')
    audio_path = os.path.abspath(audio_path)
    
    # Step 1: Transcription
    try:
        transcription = test_transcription(audio_path)
    except Exception as e:
        print(f"\n  ✗ TRANSCRIPTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Step 2: Full pipeline
    try:
        snapshot = asyncio.run(test_full_pipeline(transcription))
    except Exception as e:
        print(f"\n  ✗ PIPELINE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("=" * 70)
    print("  END-TO-END TEST COMPLETE ✓")
    print("=" * 70)


if __name__ == "__main__":
    main()
