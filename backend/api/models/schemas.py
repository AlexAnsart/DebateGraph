"""
DebateGraph — Pydantic schemas for the API and pipeline.
Mirrors the frontend TypeScript types in frontend/src/types.ts.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────

class ClaimType(str, Enum):
    PREMISE = "premise"
    CONCLUSION = "conclusion"
    CONCESSION = "concession"
    REBUTTAL = "rebuttal"


class EdgeType(str, Enum):
    SUPPORT = "support"
    ATTACK = "attack"
    UNDERCUT = "undercut"
    REFORMULATION = "reformulation"
    IMPLICATION = "implication"


class FactCheckVerdict(str, Enum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    UNVERIFIABLE = "unverifiable"
    PARTIALLY_TRUE = "partially_true"
    PENDING = "pending"


class FallacyType(str, Enum):
    STRAWMAN = "strawman"
    GOAL_POST_MOVING = "goal_post_moving"
    CIRCULAR_REASONING = "circular_reasoning"
    AD_HOMINEM = "ad_hominem"
    SLIPPERY_SLOPE = "slippery_slope"
    APPEAL_TO_EMOTION = "appeal_to_emotion"
    FALSE_DILEMMA = "false_dilemma"
    RED_HERRING = "red_herring"
    APPEAL_TO_AUTHORITY = "appeal_to_authority"
    HASTY_GENERALIZATION = "hasty_generalization"
    TU_QUOQUE = "tu_quoque"
    EQUIVOCATION = "equivocation"
    NONE = "none"


# ─── Transcription ──────────────────────────────────────────

class TranscriptionSegment(BaseModel):
    speaker: str
    text: str
    start: float
    end: float


class TranscriptionResult(BaseModel):
    segments: list[TranscriptionSegment]
    language: str = "en"
    num_speakers: int = 1


# ─── Claims & Relations ────────────────────────────────────

class Claim(BaseModel):
    id: str
    speaker: str
    text: str
    claim_type: ClaimType
    is_factual: bool = False
    segment_index: int = 0
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0
    confidence: float = 0.7


class ClaimRelation(BaseModel):
    source_id: str
    target_id: str
    relation_type: EdgeType
    confidence: float = 0.7


# ─── Annotations ────────────────────────────────────────────

class FallacyAnnotation(BaseModel):
    claim_id: str
    fallacy_type: FallacyType
    severity: float = 0.5
    explanation: str = ""
    socratic_question: str = ""
    related_claim_ids: list[str] = Field(default_factory=list)


class FactCheckResult(BaseModel):
    claim_id: str
    verdict: FactCheckVerdict = FactCheckVerdict.PENDING
    confidence: float = 0.0
    sources: list[str] = Field(default_factory=list)
    explanation: str = ""


# ─── Graph Snapshot ─────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    full_text: Optional[str] = None
    speaker: str
    claim_type: ClaimType
    timestamp_start: float
    timestamp_end: float
    confidence: float
    is_factual: bool
    factcheck_verdict: FactCheckVerdict = FactCheckVerdict.PENDING
    factcheck: Optional[FactCheckResult] = None
    fallacies: list[FallacyAnnotation] = Field(default_factory=list)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation_type: EdgeType
    confidence: float


class SpeakerRigorScore(BaseModel):
    speaker: str
    overall_score: float
    supported_ratio: float
    fallacy_count: int
    fallacy_penalty: float
    factcheck_positive_rate: float
    internal_consistency: float
    direct_response_rate: float


class GraphSnapshot(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    rigor_scores: list[SpeakerRigorScore] = Field(default_factory=list)
    cycles_detected: list[list[str]] = Field(default_factory=list)


# ─── API Responses ──────────────────────────────────────────

class UploadResponse(BaseModel):
    job_id: str
    status: str
    message: str


class AnalysisStatus(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    transcription: Optional[TranscriptionResult] = None
    graph: Optional[GraphSnapshot] = None
    error: Optional[str] = None
