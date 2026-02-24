"""
Test script: upload demos/obama_romney_10min.mp3 via the real API,
poll until complete, then verify the DB snapshot.
Logs everything to logs/run_test_<timestamp>.log
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from pathlib import Path

# ─── Setup logging ───────────────────────────────────────────
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"run_test_{ts}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
log = logging.getLogger("test")

BASE_URL = "http://localhost:8000"
AUDIO_FILE = Path(__file__).parent.parent / "demos" / "obama_romney_10min.mp3"


def main():
    log.info("=" * 60)
    log.info("DebateGraph — Full Pipeline Test")
    log.info(f"Audio: {AUDIO_FILE}")
    log.info(f"Log:   {log_file}")
    log.info("=" * 60)

    # ── 1. Health check ──────────────────────────────────────
    log.info("[1/5] Health check...")
    r = requests.get(f"{BASE_URL}/api/health")
    health = r.json()
    log.info(f"  Status: {health['status']}")
    log.info(f"  Anthropic: {health['anthropic_configured']}")
    log.info(f"  Tavily:    {health['tavily_configured']}")
    assert health["anthropic_configured"], "ANTHROPIC_API_KEY not configured!"
    assert health["tavily_configured"], "TAVILY_API_KEY not configured!"

    # ── 2. Upload file ───────────────────────────────────────
    log.info(f"[2/5] Uploading {AUDIO_FILE.name} ({AUDIO_FILE.stat().st_size / 1e6:.1f} MB)...")
    t0 = time.time()
    with open(AUDIO_FILE, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": (AUDIO_FILE.name, f, "audio/mpeg")},
            timeout=60,
        )
    r.raise_for_status()
    upload_resp = r.json()
    job_id = upload_resp["job_id"]
    log.info(f"  Job ID: {job_id}")
    log.info(f"  Upload time: {time.time() - t0:.1f}s")

    # ── 3. Poll status ───────────────────────────────────────
    log.info("[3/5] Polling status (this takes ~7-10 minutes)...")
    last_status = ""
    last_progress = -1
    poll_start = time.time()

    while True:
        time.sleep(5)
        try:
            r = requests.get(f"{BASE_URL}/api/status/{job_id}", timeout=10)
            status_data = r.json()
        except Exception as e:
            log.warning(f"  Poll error: {e}")
            continue

        status = status_data.get("status", "?")
        progress = status_data.get("progress", 0)
        elapsed = time.time() - poll_start

        if status != last_status or abs(progress - last_progress) > 0.05:
            log.info(f"  [{elapsed:5.0f}s] status={status} progress={progress*100:.0f}%")
            last_status = status
            last_progress = progress

        if status == "complete":
            log.info(f"  ✅ Complete in {elapsed:.0f}s")
            break
        elif status == "error":
            log.error(f"  ❌ Pipeline error: {status_data.get('error')}")
            sys.exit(1)
        elif elapsed > 900:  # 15 min timeout
            log.error("  ❌ Timeout after 15 minutes")
            sys.exit(1)

    # ── 4. Verify snapshot from DB ───────────────────────────
    log.info("[4/5] Loading snapshot from DB...")
    r = requests.get(f"{BASE_URL}/api/snapshot/{job_id}", timeout=10)
    r.raise_for_status()
    snap_resp = r.json()

    graph = snap_resp["graph"]
    transcription = snap_resp.get("transcription")
    meta = snap_resp.get("meta", {})

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    rigor = graph.get("rigor_scores", [])
    cycles = graph.get("cycles_detected", [])
    fallacies_all = [f for n in nodes for f in n.get("fallacies", [])]
    factchecked = [n for n in nodes if n.get("factcheck_verdict") not in (None, "pending")]

    log.info(f"  Nodes:       {len(nodes)}")
    log.info(f"  Edges:       {len(edges)}")
    log.info(f"  Fallacies:   {len(fallacies_all)}")
    log.info(f"  Fact-checks: {len(factchecked)}")
    log.info(f"  Cycles:      {len(cycles)}")
    log.info(f"  Speakers:    {meta.get('speakers', [])}")

    # Rigor scores
    log.info("  Rigor scores:")
    for r_score in rigor:
        log.info(
            f"    {r_score['speaker']}: {r_score['overall_score']*100:.0f}% "
            f"(fallacies={r_score['fallacy_count']}, "
            f"factcheck+={r_score['factcheck_positive_rate']*100:.0f}%)"
        )

    # Fallacy breakdown
    if fallacies_all:
        from collections import Counter
        ftypes = Counter(f["fallacy_type"] for f in fallacies_all)
        log.info("  Fallacy types:")
        for ftype, count in ftypes.most_common():
            log.info(f"    {ftype}: {count}")

    # Fact-check verdict breakdown
    if factchecked:
        from collections import Counter
        verdicts = Counter(n["factcheck_verdict"] for n in factchecked)
        log.info("  Fact-check verdicts:")
        for verdict, count in verdicts.most_common():
            log.info(f"    {verdict}: {count}")

    # Sample claims
    log.info("  Sample claims (first 5):")
    for n in nodes[:5]:
        fc = n.get("factcheck_verdict", "—")
        fallacy_count = len(n.get("fallacies", []))
        log.info(
            f"    [{n['id']}] {n['speaker']} ({n['claim_type']}) "
            f"fc={fc} fallacies={fallacy_count}: {n['label'][:70]}"
        )

    # Transcription check
    if transcription:
        segs = transcription.get("segments", [])
        log.info(f"  Transcription: {len(segs)} segments, "
                 f"{transcription.get('num_speakers')} speakers, "
                 f"lang={transcription.get('language')}")

    # ── 5. Verify jobs list ──────────────────────────────────
    log.info("[5/5] Verifying jobs list in DB...")
    r = requests.get(f"{BASE_URL}/api/jobs", timeout=10)
    jobs = r.json()
    log.info(f"  Total jobs in DB: {len(jobs)}")
    our_job = next((j for j in jobs if j["id"] == job_id), None)
    assert our_job is not None, "Job not found in DB list!"
    log.info(f"  Our job: status={our_job['status']}, "
             f"nodes={our_job.get('num_nodes')}, "
             f"edges={our_job.get('num_edges')}")

    # Save snapshot to file for reference
    out_file = log_dir / f"snapshot_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(snap_resp, f, indent=2, ensure_ascii=False)
    log.info(f"  Snapshot saved to: {out_file}")

    total_time = time.time() - t0
    log.info("=" * 60)
    log.info("✅ ALL TESTS PASSED")
    log.info(f"Total time: {total_time:.0f}s ({total_time/60:.1f} min)")
    log.info(f"DB Viewer:  http://localhost:8000/db")
    log.info(f"Snapshot:   http://localhost:8000/db/snapshot/{job_id}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
