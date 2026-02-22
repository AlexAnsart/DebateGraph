/**
 * TypeScript types mirroring the backend Pydantic schemas.
 */

// ─── Enums ──────────────────────────────────────────────────

export type ClaimType = "premise" | "conclusion" | "concession" | "rebuttal";

export type EdgeType =
  | "support"
  | "attack"
  | "undercut"
  | "reformulation"
  | "implication";

export type FactCheckVerdict =
  | "supported"
  | "refuted"
  | "unverifiable"
  | "partially_true"
  | "pending";

export type FallacyType =
  | "strawman"
  | "goal_post_moving"
  | "circular_reasoning"
  | "ad_hominem"
  | "slippery_slope"
  | "appeal_to_emotion"
  | "false_dilemma"
  | "red_herring"
  | "appeal_to_authority"
  | "hasty_generalization"
  | "tu_quoque"
  | "equivocation"
  | "none";


// ─── Transcription ──────────────────────────────────────────

export interface TranscriptionSegment {
  speaker: string;
  text: string;
  start: number;
  end: number;
}

export interface TranscriptionResult {
  segments: TranscriptionSegment[];
  language: string;
  num_speakers: number;
}

// ─── Fallacy ────────────────────────────────────────────────

export interface FallacyAnnotation {
  claim_id: string;
  fallacy_type: FallacyType;
  severity: number;
  explanation: string;
  socratic_question: string;
  related_claim_ids: string[];
}

// ─── Graph ──────────────────────────────────────────────────

export interface FactCheckResult {
  claim_id: string;
  verdict: FactCheckVerdict;
  confidence: number;
  sources: string[];
  explanation: string;
}

export interface GraphNode {
  id: string;
  label: string;
  speaker: string;
  claim_type: ClaimType;
  timestamp_start: number;
  timestamp_end: number;
  confidence: number;
  is_factual: boolean;
  factcheck_verdict: FactCheckVerdict;
  factcheck: FactCheckResult | null;
  fallacies: FallacyAnnotation[];
}

export interface GraphEdge {
  source: string;
  target: string;
  relation_type: EdgeType;
  confidence: number;
}

export interface SpeakerRigorScore {
  speaker: string;
  overall_score: number;
  supported_ratio: number;
  fallacy_count: number;
  fallacy_penalty: number;
  factcheck_positive_rate: number;
  internal_consistency: number;
  direct_response_rate: number;
}

export interface GraphSnapshot {
  nodes: GraphNode[];
  edges: GraphEdge[];
  rigor_scores: SpeakerRigorScore[];
  cycles_detected: string[][];
}

// ─── API Responses ──────────────────────────────────────────

export interface UploadResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface AnalysisStatus {
  job_id: string;
  status: string;
  progress: number;
  transcription: TranscriptionResult | null;
  graph: GraphSnapshot | null;
  error: string | null;
}

export interface DemoResponse {
  status: string;
  transcription: TranscriptionResult;
  graph: GraphSnapshot;
}

export interface HealthResponse {
  status: string;
  version: string;
  whisper_available: boolean;
  anthropic_configured: boolean;
  tavily_configured: boolean;
}

// ─── UI State ───────────────────────────────────────────────

export interface SelectedNode {
  node: GraphNode;
  position: { x: number; y: number };
}

// ─── Color Maps ─────────────────────────────────────────────

export const EDGE_COLORS: Record<EdgeType, string> = {
  support: "#22c55e",
  attack: "#ef4444",
  undercut: "#a855f7",
  reformulation: "#6b7280",
  implication: "#3b82f6",
};

export const SPEAKER_COLORS: string[] = [
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#10b981", // emerald
  "#ec4899", // pink
  "#8b5cf6", // violet
  "#06b6d4", // cyan
];

export const VERDICT_COLORS: Record<FactCheckVerdict, string> = {
  supported: "#22c55e",
  refuted: "#ef4444",
  unverifiable: "#6b7280",
  partially_true: "#f59e0b",
  pending: "#6b7280",
};

export const VERDICT_ICONS: Record<FactCheckVerdict, string> = {
  supported: "✓",
  refuted: "✗",
  unverifiable: "?",
  partially_true: "~",
  pending: "…",
};
