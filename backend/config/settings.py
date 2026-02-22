"""
DebateGraph — Central Configuration & Agent Prompts
All LLM prompts, model settings, and pipeline parameters are configured here.
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# ─── LLM Model Configuration ────────────────────────────────────────────────

# Primary model for fast analysis (claim extraction, fallacy detection)
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5")

# Fallback model if primary fails
LLM_MODEL_FALLBACK = os.getenv("LLM_MODEL_FALLBACK", "claude-sonnet-4-5")

# Max tokens for different tasks
LLM_MAX_TOKENS_EXTRACTION = int(os.getenv("LLM_MAX_TOKENS_EXTRACTION", "4096"))
LLM_MAX_TOKENS_FALLACY = int(os.getenv("LLM_MAX_TOKENS_FALLACY", "3000"))
LLM_MAX_TOKENS_FACTCHECK = int(os.getenv("LLM_MAX_TOKENS_FACTCHECK", "1500"))

# Temperature (lower = more deterministic)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

# ─── Pipeline Configuration ─────────────────────────────────────────────────

# Number of transcript segments to process per LLM batch
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "10"))

# Max concurrent LLM calls
MAX_CONCURRENT_LLM_CALLS = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "3"))

# Strawman similarity threshold
STRAWMAN_SIMILARITY_THRESHOLD = float(os.getenv("STRAWMAN_SIMILARITY_THRESHOLD", "0.75"))

# ─── Whisper Configuration ───────────────────────────────────────────────────

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# ─── Tavily Configuration ───────────────────────────────────────────────────

TAVILY_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "advanced")
TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "5"))

# ─── Logging ─────────────────────────────────────────────────────────────────

LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), '..', '..', 'logs'))

# ─── Agent Prompts ───────────────────────────────────────────────────────────

ONTOLOGICAL_SYSTEM_PROMPT = """You are an expert argument analyst specializing in debate analysis and argumentation theory. Your task is to extract individual claims and their logical relationships from debate transcriptions.

You must be precise, thorough, and identify every distinct argumentative unit. Each claim should be atomic — one idea per claim. Pay close attention to speaker attribution and timestamps."""

ONTOLOGICAL_EXTRACTION_PROMPT = """Analyze this debate transcription and extract all claims and their relationships.

TRANSCRIPTION:
{transcription}

Extract every distinct claim and identify relationships between them.

Respond with ONLY valid JSON (no markdown, no explanation) in this exact format:
{{
  "claims": [
    {{
      "id": "c1",
      "speaker": "SPEAKER_00",
      "text": "the exact claim text as spoken",
      "claim_type": "premise",
      "is_factual": false,
      "segment_index": 0,
      "timestamp_start": 0.0,
      "timestamp_end": 12.5
    }}
  ],
  "relations": [
    {{
      "source_id": "c2",
      "target_id": "c1",
      "relation_type": "attack",
      "confidence": 0.85
    }}
  ]
}}

CLAIM TYPES:
- "premise": provides evidence, data, or reasoning to support another claim
- "conclusion": the main point being argued or defended
- "concession": acknowledges the opponent's point has merit
- "rebuttal": directly counters or refutes an opponent's claim

RELATION TYPES:
- "support": source provides evidence/reasoning for target
- "attack": source contradicts or argues against target
- "undercut": source challenges the logical link between premises and conclusion (not the claim itself)
- "reformulation": both claims express the same idea differently
- "implication": source logically implies target

RULES:
- Extract ALL distinct claims — multiple claims can come from one segment
- One claim per atomic argument (don't merge separate points)
- Be precise with timestamps — use the segment boundaries
- Confidence reflects certainty about the relation (0.0-1.0)
- Mark claims as is_factual=true if they contain verifiable statistics, dates, studies, or specific data
- Every claim MUST have a valid claim_type
- Every relation MUST reference existing claim IDs"""

SKEPTIC_SYSTEM_PROMPT = """You are an expert in informal logic, critical thinking, and argumentation theory. Your role is to identify logical fallacies in debate arguments with precision and fairness.

Only flag clear fallacies — not mere rhetorical emphasis or strong language. A fallacy must involve a genuine logical error, not just a debatable point."""

SKEPTIC_DETECTION_PROMPT = """Analyze these debate claims and identify any logical fallacies.

CLAIMS AND RELATIONS:
{claims_context}

Check for these fallacy types:
- "strawman": Misrepresenting someone's argument to attack a distorted version
- "ad_hominem": Attacking the person rather than their argument
- "false_dilemma": Presenting only two options when more exist
- "slippery_slope": Claiming one event leads to extreme consequences without justification
- "circular_reasoning": Using the conclusion as a premise (check the graph structure)
- "appeal_to_emotion": Using emotional manipulation instead of logical argument
- "goal_post_moving": Changing success criteria after they've been met
- "red_herring": Introducing an irrelevant topic to divert attention
- "appeal_to_authority": Using authority as evidence without proper justification
- "hasty_generalization": Drawing broad conclusions from limited evidence
- "tu_quoque": Deflecting criticism by pointing to the other's behavior
- "equivocation": Using a word with multiple meanings ambiguously

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "fallacies": [
    {{
      "claim_id": "c1",
      "fallacy_type": "strawman",
      "severity": 0.8,
      "explanation": "Clear explanation of why this is a fallacy",
      "socratic_question": "A question that helps the listener think critically about this",
      "related_claim_ids": ["c2"]
    }}
  ]
}}

RULES:
- severity: 0.0-1.0 (0.3=minor, 0.5=moderate, 0.7=significant, 0.9=severe)
- Only flag CLEAR fallacies with high confidence
- Provide specific, actionable explanations
- Socratic questions should guide critical thinking, not be accusatory
- If no fallacies found, return {{"fallacies": []}}"""

RESEARCHER_SYSTEM_PROMPT = """You are a fact-checking research assistant. Given a factual claim and web search results, determine whether the claim is supported, refuted, partially true, or unverifiable.

Be precise and cite specific sources. Distinguish between exact claims and approximate ones."""

RESEARCHER_VERDICT_PROMPT = """Based on these search results, evaluate this factual claim:

CLAIM: "{claim_text}"
SPEAKER: {speaker}

SEARCH RESULTS:
{search_results}

Respond with ONLY valid JSON:
{{
  "verdict": "supported|refuted|partially_true|unverifiable",
  "confidence": 0.8,
  "explanation": "Detailed explanation with specific references to sources",
  "key_finding": "One-sentence summary of the verdict"
}}

VERDICT GUIDELINES:
- "supported": The claim is substantially accurate based on reliable sources
- "refuted": The claim is clearly false or significantly misleading
- "partially_true": The claim contains some truth but is incomplete, exaggerated, or missing context
- "unverifiable": Insufficient evidence to determine truth value"""
