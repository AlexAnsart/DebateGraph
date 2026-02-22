"""Test the demo endpoint with real Claude API calls."""
import urllib.request
import json
import time

print("Testing /api/demo endpoint...")
start = time.time()

req = urllib.request.Request(
    "http://localhost:8001/api/demo",
    method="POST",
    data=b"",
    headers={"Content-Type": "application/json"},
)

r = urllib.request.urlopen(req, timeout=120)
data = json.loads(r.read())
elapsed = time.time() - start

print(f"\nStatus: {data['status']} ({elapsed:.1f}s)")

g = data["graph"]
print(f"Nodes: {len(g['nodes'])}")
print(f"Edges: {len(g['edges'])}")
print(f"Rigor scores: {len(g['rigor_scores'])}")
print(f"Cycles: {len(g['cycles_detected'])}")

print("\n--- NODES ---")
for n in g["nodes"]:
    fallacies = [f["fallacy_type"] for f in n.get("fallacies", [])]
    fc = n.get("factcheck_verdict", "pending")
    print(f"  [{n['id']}] {n['speaker']} ({n['claim_type']}, fc={fc}): {n['label'][:70]}...")
    if fallacies:
        print(f"         FALLACIES: {fallacies}")

print("\n--- EDGES ---")
for e in g["edges"]:
    print(f"  {e['source']} --[{e['relation_type']}]--> {e['target']} (conf={e['confidence']})")

print("\n--- RIGOR SCORES ---")
for s in g["rigor_scores"]:
    print(f"  {s['speaker']}: overall={s['overall_score']}, "
          f"fallacies={s['fallacy_count']}, "
          f"factcheck_rate={s['factcheck_positive_rate']}")

print(f"\nTotal time: {elapsed:.1f}s")
