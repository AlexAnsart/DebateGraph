"""
In-memory argument graph store using NetworkX.
Manages the directed graph of claims and their relations.
"""

import logging
from typing import Optional

import networkx as nx

from api.models.schemas import (
    Claim,
    ClaimRelation,
    ClaimType,
    EdgeType,
    FallacyAnnotation,
    FactCheckResult,
    FactCheckVerdict,
    SpeakerRigorScore,
    GraphNode,
    GraphEdge,
    GraphSnapshot,
)

logger = logging.getLogger(__name__)


class DebateGraphStore:
    """
    In-memory directed graph store for a single debate.
    Each node is a Claim, each edge is a ClaimRelation.
    Annotations (fallacies, fact-checks) are stored as node/edge attributes.
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._claims: dict[str, Claim] = {}
        self._fallacies: dict[str, list[FallacyAnnotation]] = {}
        self._factchecks: dict[str, FactCheckResult] = {}

    # ─── Node Operations ────────────────────────────────────

    def add_claim(self, claim: Claim) -> None:
        """Add a claim as a node in the graph."""
        self._claims[claim.id] = claim
        self.graph.add_node(
            claim.id,
            speaker=claim.speaker,
            text=claim.text,
            claim_type=claim.claim_type.value,
            timestamp_start=claim.timestamp_start,
            timestamp_end=claim.timestamp_end,
            confidence=claim.confidence,
            is_factual=claim.is_factual,
        )
        logger.debug(f"Added claim node: {claim.id} ({claim.claim_type})")

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Retrieve a claim by ID."""
        return self._claims.get(claim_id)

    def get_all_claims(self) -> list[Claim]:
        """Get all claims in the graph."""
        return list(self._claims.values())

    def get_claims_by_speaker(self, speaker: str) -> list[Claim]:
        """Get all claims made by a specific speaker."""
        return [c for c in self._claims.values() if c.speaker == speaker]

    def get_speakers(self) -> list[str]:
        """Get list of unique speakers."""
        return list(set(c.speaker for c in self._claims.values()))

    # ─── Edge Operations ────────────────────────────────────

    def add_relation(self, relation: ClaimRelation) -> None:
        """Add a directed relation (edge) between two claims."""
        if relation.source_id not in self._claims:
            logger.warning(f"Source claim {relation.source_id} not found")
            return
        if relation.target_id not in self._claims:
            logger.warning(f"Target claim {relation.target_id} not found")
            return

        self.graph.add_edge(
            relation.source_id,
            relation.target_id,
            relation_type=relation.relation_type.value,
            confidence=relation.confidence,
        )
        logger.debug(
            f"Added edge: {relation.source_id} --[{relation.relation_type}]--> {relation.target_id}"
        )

    def get_relations(self) -> list[ClaimRelation]:
        """Get all relations in the graph."""
        relations = []
        for src, tgt, data in self.graph.edges(data=True):
            relations.append(ClaimRelation(
                source_id=src,
                target_id=tgt,
                relation_type=EdgeType(data.get("relation_type", "support")),
                confidence=data.get("confidence", 0.7),
            ))
        return relations

    # ─── Annotation Operations ──────────────────────────────

    def add_fallacy(self, annotation: FallacyAnnotation) -> None:
        """Add a fallacy annotation to a claim."""
        if annotation.claim_id not in self._fallacies:
            self._fallacies[annotation.claim_id] = []
        self._fallacies[annotation.claim_id].append(annotation)
        logger.debug(f"Added fallacy {annotation.fallacy_type} to claim {annotation.claim_id}")

    def get_fallacies(self, claim_id: str) -> list[FallacyAnnotation]:
        """Get all fallacy annotations for a claim."""
        return self._fallacies.get(claim_id, [])

    def get_all_fallacies(self) -> list[FallacyAnnotation]:
        """Get all fallacy annotations across all claims."""
        all_fallacies = []
        for fallacies in self._fallacies.values():
            all_fallacies.extend(fallacies)
        return all_fallacies

    def add_factcheck(self, result: FactCheckResult) -> None:
        """Add a fact-check result to a claim."""
        self._factchecks[result.claim_id] = result
        logger.debug(f"Added fact-check {result.verdict} to claim {result.claim_id}")

    def get_factcheck(self, claim_id: str) -> Optional[FactCheckResult]:
        """Get fact-check result for a claim."""
        return self._factchecks.get(claim_id)

    # ─── Graph Metrics ──────────────────────────────────────

    @property
    def num_nodes(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def num_edges(self) -> int:
        return self.graph.number_of_edges()

    # ─── Rigor Score Computation ────────────────────────────

    def compute_rigor_scores(self) -> list[SpeakerRigorScore]:
        """
        Compute composite rigor score for each speaker.
        Based on: supported ratio, fallacy count, fact-check rate,
        internal consistency, and direct response rate.
        """
        speakers = self.get_speakers()
        scores = []

        for speaker in speakers:
            claims = self.get_claims_by_speaker(speaker)
            if not claims:
                continue

            total_claims = len(claims)

            # Supported ratio: claims that have at least one support edge
            supported = sum(
                1 for c in claims
                if any(
                    self.graph.has_edge(other, c.id)
                    and self.graph[other][c.id].get("relation_type") == "support"
                    for other in self.graph.predecessors(c.id)
                )
            )
            supported_ratio = supported / total_claims if total_claims > 0 else 0.0

            # Fallacy count and penalty
            fallacy_count = sum(len(self.get_fallacies(c.id)) for c in claims)
            fallacy_penalty = min(fallacy_count * 0.1, 0.5)  # max 50% penalty

            # Fact-check positive rate
            factual_claims = [c for c in claims if c.is_factual]
            if factual_claims:
                checked = [
                    c for c in factual_claims
                    if c.id in self._factchecks
                    and self._factchecks[c.id].verdict == FactCheckVerdict.SUPPORTED
                ]
                factcheck_rate = len(checked) / len(factual_claims)
            else:
                factcheck_rate = 0.5  # neutral if no factual claims

            # Internal consistency: check for self-contradictions
            contradictions = 0
            for c1 in claims:
                for c2 in claims:
                    if c1.id != c2.id and self.graph.has_edge(c1.id, c2.id):
                        edge_data = self.graph[c1.id][c2.id]
                        if edge_data.get("relation_type") == "attack":
                            contradictions += 1
            consistency = max(0.0, 1.0 - (contradictions * 0.15))

            # Direct response rate: how often this speaker responds to opponent claims
            other_speakers_claims = [
                c for c in self._claims.values() if c.speaker != speaker
            ]
            direct_responses = 0
            for c in claims:
                for other_c in other_speakers_claims:
                    if self.graph.has_edge(c.id, other_c.id) or self.graph.has_edge(other_c.id, c.id):
                        direct_responses += 1
                        break
            response_rate = direct_responses / total_claims if total_claims > 0 else 0.0

            # Composite score
            overall = (
                supported_ratio * 0.25
                + (1.0 - fallacy_penalty) * 0.25
                + factcheck_rate * 0.20
                + consistency * 0.15
                + response_rate * 0.15
            )

            scores.append(SpeakerRigorScore(
                speaker=speaker,
                overall_score=round(overall, 3),
                supported_ratio=round(supported_ratio, 3),
                fallacy_count=fallacy_count,
                fallacy_penalty=round(fallacy_penalty, 3),
                factcheck_positive_rate=round(factcheck_rate, 3),
                internal_consistency=round(consistency, 3),
                direct_response_rate=round(response_rate, 3),
            ))

        return scores

    # ─── Snapshot for Frontend ──────────────────────────────

    def to_snapshot(self) -> GraphSnapshot:
        """
        Export the current graph state as a GraphSnapshot for the frontend.
        """
        nodes = []
        for claim_id, claim in self._claims.items():
            fc = self._factchecks.get(claim_id)
            nodes.append(GraphNode(
                id=claim.id,
                label=claim.text[:80] + ("..." if len(claim.text) > 80 else ""),
                speaker=claim.speaker,
                claim_type=claim.claim_type,
                timestamp_start=claim.timestamp_start,
                timestamp_end=claim.timestamp_end,
                confidence=claim.confidence,
                is_factual=claim.is_factual,
                factcheck_verdict=fc.verdict if fc else FactCheckVerdict.PENDING,
                factcheck=fc,
                fallacies=self.get_fallacies(claim_id),
            ))

        edges = []
        for src, tgt, data in self.graph.edges(data=True):
            edges.append(GraphEdge(
                source=src,
                target=tgt,
                relation_type=EdgeType(data.get("relation_type", "support")),
                confidence=data.get("confidence", 0.7),
            ))

        from graph.algorithms import detect_cycles
        cycles = detect_cycles(self.graph)

        return GraphSnapshot(
            nodes=nodes,
            edges=edges,
            rigor_scores=self.compute_rigor_scores(),
            cycles_detected=cycles,
        )
