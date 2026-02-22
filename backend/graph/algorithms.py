"""
Graph algorithms for argumentative analysis.
Implements cycle detection, strawman detection, semantic drift tracking,
and other structural analysis on the argument graph.
"""

import logging
from typing import Optional

import networkx as nx

logger = logging.getLogger(__name__)


# ─── Cycle Detection (Circular Reasoning) ───────────────────

def detect_cycles(graph: nx.DiGraph) -> list[list[str]]:
    """
    Detect all simple cycles in the argument graph using DFS.
    Circular reasoning manifests as cycles: A supports B supports C supports A.

    Complexity: O(V+E) for cycle detection.

    Returns:
        List of cycles, where each cycle is a list of node IDs.
    """
    try:
        cycles = list(nx.simple_cycles(graph))
        if cycles:
            logger.info(f"Detected {len(cycles)} cycle(s) in argument graph")
        return cycles
    except Exception as e:
        logger.error(f"Cycle detection failed: {e}")
        return []


def explain_cycle(graph: nx.DiGraph, cycle: list[str]) -> str:
    """
    Generate a human-readable explanation of a detected cycle.

    Args:
        graph: The argument graph
        cycle: List of node IDs forming the cycle

    Returns:
        Natural language explanation of the circular reasoning
    """
    if len(cycle) < 2:
        return "Trivial cycle detected."

    parts = []
    for i in range(len(cycle)):
        src = cycle[i]
        tgt = cycle[(i + 1) % len(cycle)]
        src_text = graph.nodes[src].get("text", src)[:60]
        tgt_text = graph.nodes[tgt].get("text", tgt)[:60]
        edge_data = graph.get_edge_data(src, tgt, default={})
        rel = edge_data.get("relation_type", "relates to")
        parts.append(f'"{src_text}..." {rel} "{tgt_text}..."')

    chain = " → ".join(parts)
    return (
        f"Circular reasoning detected: {chain}. "
        f"This forms a loop where the conclusion presupposes one of its own premises. "
        f"To break this cycle, at least one claim needs independent justification."
    )


# ─── Strawman Detection ─────────────────────────────────────

def detect_strawman_candidates(
    graph: nx.DiGraph,
    similarity_threshold: float = 0.75,
) -> list[dict]:
    """
    Detect potential strawman arguments by finding attack edges
    where the attacker may be misrepresenting the original claim.

    A strawman requires:
    1. Speaker B attacks a claim that relates to Speaker A's original claim
    2. The semantic similarity between A's original and B's characterization is low
    3. B's intent is refutational

    This function identifies structural candidates; semantic verification
    requires embeddings (done in the Skeptic Agent).

    Returns:
        List of candidate dicts with original_claim_id, attacking_claim_id, speaker info
    """
    candidates = []

    for src, tgt, data in graph.edges(data=True):
        if data.get("relation_type") != "attack":
            continue

        src_speaker = graph.nodes[src].get("speaker", "")
        tgt_speaker = graph.nodes[tgt].get("speaker", "")

        # Strawman: different speakers, attack edge
        if src_speaker != tgt_speaker:
            candidates.append({
                "attacking_claim_id": src,
                "original_claim_id": tgt,
                "attacker": src_speaker,
                "original_speaker": tgt_speaker,
                "attacking_text": graph.nodes[src].get("text", ""),
                "original_text": graph.nodes[tgt].get("text", ""),
            })

    logger.debug(f"Found {len(candidates)} strawman candidates")
    return candidates


# ─── Goal-Post Moving Detection ─────────────────────────────

def detect_goalpost_moving(
    graph: nx.DiGraph,
) -> list[dict]:
    """
    Detect potential goal-post moving by tracking how a speaker's
    claims on a topic evolve over time.

    Goal-post moving occurs when:
    1. Speaker A makes claim X (win condition)
    2. Opponent refutes X with evidence
    3. Speaker A shifts to claim Y without conceding X

    Returns:
        List of potential goal-post shifts with claim chains
    """
    shifts = []

    # Group claims by speaker
    speakers: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        speaker = data.get("speaker", "unknown")
        if speaker not in speakers:
            speakers[speaker] = []
        speakers[speaker].append(node_id)

    for speaker, claim_ids in speakers.items():
        # Sort by timestamp
        sorted_claims = sorted(
            claim_ids,
            key=lambda nid: graph.nodes[nid].get("timestamp_start", 0),
        )

        for i, claim_id in enumerate(sorted_claims):
            # Check if this claim was attacked/refuted
            attackers = [
                pred for pred in graph.predecessors(claim_id)
                if graph[pred][claim_id].get("relation_type") == "attack"
                and graph.nodes[pred].get("speaker") != speaker
            ]

            if not attackers:
                continue

            # Check if the speaker conceded (has a concession-type claim after the attack)
            later_claims = sorted_claims[i + 1:]
            conceded = any(
                graph.nodes[lc].get("claim_type") == "concession"
                for lc in later_claims
            )

            if not conceded and later_claims:
                # Speaker was attacked but didn't concede and made new claims
                shifts.append({
                    "speaker": speaker,
                    "original_claim_id": claim_id,
                    "original_text": graph.nodes[claim_id].get("text", ""),
                    "attacked_by": [
                        {
                            "claim_id": a,
                            "text": graph.nodes[a].get("text", ""),
                        }
                        for a in attackers
                    ],
                    "subsequent_claims": [
                        {
                            "claim_id": lc,
                            "text": graph.nodes[lc].get("text", ""),
                        }
                        for lc in later_claims[:3]  # limit to next 3
                    ],
                })

    logger.debug(f"Found {len(shifts)} potential goal-post shifts")
    return shifts


# ─── Topic Drift Detection ──────────────────────────────────

def detect_topic_drift(
    graph: nx.DiGraph,
    window_size: int = 5,
) -> list[dict]:
    """
    Detect when the debate drifts away from the original topic.
    Analyzes connectivity between recent claims and the initial claims.

    Args:
        graph: The argument graph
        window_size: Number of recent claims to consider

    Returns:
        List of drift events with timing and topic info
    """
    all_nodes = sorted(
        graph.nodes(),
        key=lambda n: graph.nodes[n].get("timestamp_start", 0),
    )

    if len(all_nodes) < window_size + 2:
        return []

    drifts = []
    initial_nodes = set(all_nodes[:window_size])

    for i in range(window_size, len(all_nodes) - window_size + 1, window_size):
        window_nodes = set(all_nodes[i:i + window_size])

        # Check connectivity between window and initial nodes
        connected = 0
        for wn in window_nodes:
            for init_n in initial_nodes:
                if nx.has_path(graph.to_undirected(), wn, init_n):
                    connected += 1
                    break

        connectivity = connected / len(window_nodes) if window_nodes else 1.0

        if connectivity < 0.5:  # Less than half connected to original topic
            window_start = min(
                graph.nodes[n].get("timestamp_start", 0) for n in window_nodes
            )
            drifts.append({
                "timestamp": window_start,
                "connectivity_to_original": round(connectivity, 2),
                "window_claims": [
                    graph.nodes[n].get("text", "")[:60] for n in window_nodes
                ],
            })

    return drifts


# ─── Graph Statistics ────────────────────────────────────────

def compute_graph_stats(graph: nx.DiGraph) -> dict:
    """Compute summary statistics about the argument graph."""
    if graph.number_of_nodes() == 0:
        return {"nodes": 0, "edges": 0}

    # Edge type distribution
    edge_types: dict[str, int] = {}
    for _, _, data in graph.edges(data=True):
        rt = data.get("relation_type", "unknown")
        edge_types[rt] = edge_types.get(rt, 0) + 1

    # Speaker distribution
    speaker_counts: dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        sp = data.get("speaker", "unknown")
        speaker_counts[sp] = speaker_counts.get(sp, 0) + 1

    # Connectivity
    undirected = graph.to_undirected()
    components = list(nx.connected_components(undirected))

    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "edge_types": edge_types,
        "speaker_distribution": speaker_counts,
        "connected_components": len(components),
        "density": round(nx.density(graph), 4),
        "cycles": len(list(nx.simple_cycles(graph))),
    }
