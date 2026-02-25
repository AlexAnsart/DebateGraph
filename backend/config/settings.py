"""
DebateGraph — Central Configuration & Agent Prompts
All LLM prompts, model settings, and pipeline parameters are configured here.
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'), override=True)

# ─── LLM Model Configuration ────────────────────────────────────────────────

# Primary model for fast analysis (claim extraction, fallacy detection)
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5")

# Fallback model if primary fails
LLM_MODEL_FALLBACK = os.getenv("LLM_MODEL_FALLBACK", "claude-haiku-4-5")

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

# ─── Speech-to-Text Configuration (OpenAI API) ──────────────────────────────

# Model: gpt-4o-transcribe-diarize (best: transcription + speaker diarization)
#        gpt-4o-transcribe (fallback: transcription only, no diarization)
#        gpt-4o-mini-transcribe (cheapest: transcription only)
STT_MODEL = os.getenv("STT_MODEL", "gpt-4o-transcribe-diarize")

# Optional prompt to improve transcription quality (context about the audio)
STT_PROMPT = os.getenv("STT_PROMPT", "This is a political debate between two candidates discussing policy issues including the economy, healthcare, education, foreign policy, and energy.")

# Legacy Whisper config (kept for local WhisperX fallback if needed)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# ─── Tavily Configuration ───────────────────────────────────────────────────

TAVILY_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "advanced")
TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "5"))

# ─── Logging ─────────────────────────────────────────────────────────────────

LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), '..', '..', 'logs'))

# ─── Upload Directory ────────────────────────────────────────────────────────
# Default: backend/uploads. Override if project is in OneDrive (e.g. %LOCALAPPDATA%\DebateGraph\uploads).
_default_upload = os.path.join(os.path.dirname(__file__), '..', 'uploads')
UPLOAD_DIR = os.path.expandvars(os.getenv("UPLOAD_DIR", _default_upload))

# ─── Agent Prompts ───────────────────────────────────────────────────────────

ONTOLOGICAL_SYSTEM_PROMPT = """You are an expert argument analyst specializing in debate analysis and argumentation theory. Your task is to extract individual claims and their logical relationships from debate transcriptions.

You must be precise, thorough, and identify every distinct argumentative unit. Each claim should be atomic — one idea per claim. Pay close attention to speaker attribution and timestamps.

In political debates, speakers frequently rebut each other and occasionally concede points. Be attentive to these dynamics — a response that contradicts or challenges the previous speaker is a REBUTTAL, and any acknowledgment of validity in the opponent's position is a CONCESSION."""

ONTOLOGICAL_EXTRACTION_PROMPT = """Analyze this debate transcription and extract all claims and their relationships.

TRANSCRIPTION:
{transcription}

Extract every distinct claim and identify relationships between them.

IMPORTANT: Skip any segment that is just a single word, filler ("uh", "um", "okay", "yeah", "oh"), or incomplete fragment with no argumentative content.

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

CLAIM TYPES (use EXACTLY one of these values):
- "premise": provides evidence, data, or reasoning to support another claim
- "conclusion": the main point being argued or defended; the speaker's core position on an issue
- "concession": acknowledges the opponent's point has merit (e.g. "that's a fair point", "I agree that...", "you're right about...")
- "rebuttal": directly counters or refutes an opponent's claim. In a debate, when Speaker B responds to Speaker A by disagreeing, challenging, or offering a counter-argument, that IS a rebuttal

CLASSIFICATION GUIDE FOR DEBATES:
- When a speaker makes a factual assertion to support their argument → "premise"
- When a speaker states their core position or what they advocate → "conclusion"
- When a speaker explicitly or implicitly disagrees with what the OTHER speaker said → "rebuttal"
- When a speaker acknowledges something the other side said is valid → "concession"
- In a two-person debate, most responses to the opponent are REBUTTALS, not premises

RELATION TYPES (use EXACTLY one of these values):
- "support": source provides evidence/reasoning for target
- "attack": source contradicts or argues against target
- "undercut": source challenges the logical link between premises and conclusion (not the claim itself)
- "reformulation": both claims express the same idea differently
- "implication": source logically implies target

CRITICAL RULES:
- relation_type MUST be one of: "support", "attack", "undercut", "reformulation", "implication" — NEVER use claim types as relation types
- claim_type MUST be one of: "premise", "conclusion", "concession", "rebuttal" — NEVER use relation types as claim types
- Extract ALL distinct claims — multiple claims can come from one segment
- One claim per atomic argument (don't merge separate points)
- Be precise with timestamps — use the segment boundaries
- Confidence reflects certainty about the relation (0.0-1.0)
- Mark claims as is_factual=true ONLY if they contain verifiable statistics, specific numbers, dates, named studies, or concrete data points. General policy arguments are NOT factual even if about economic topics
- Every claim MUST have a valid claim_type
- Every relation MUST reference existing claim IDs
- Do NOT extract single-word utterances, filler words, or incomplete fragments as claims
- When two speakers are debating, link rebuttals to the claims they are responding to with "attack" relations"""

SKEPTIC_SYSTEM_PROMPT = """You are an expert in informal logic, critical thinking, and argumentation theory. Your role is to identify logical fallacies in debate arguments with precision and fairness.

CRITICAL: You must be HIGHLY SELECTIVE. Only flag genuine, clear-cut logical fallacies — NOT normal rhetorical techniques, strong opinions, or persuasive language. In political debates, speakers routinely use generalizations, emotional appeals, and authority references as standard rhetoric. These are NORMAL debate techniques, not fallacies, unless they involve a clear logical error.

A fallacy must involve a genuine logical error, not just a debatable point or rhetorical style."""

SKEPTIC_DETECTION_PROMPT = """Analyze these debate claims and identify any logical fallacies.

CLAIMS AND RELATIONS:
{claims_context}

Check for these fallacy types:
- "strawman": Misrepresenting someone's argument to attack a distorted version. REQUIRES: The speaker must demonstrably distort what the opponent actually said. Simply disagreeing or paraphrasing is NOT a strawman.
- "ad_hominem": Attacking the person rather than their argument. REQUIRES: A direct personal attack used AS the argument (not alongside an argument).
- "false_dilemma": Presenting only two options when more exist. REQUIRES: Explicitly framing a choice as binary when it clearly isn't.
- "slippery_slope": Claiming one event leads to extreme consequences without justification. REQUIRES: A chain of unsubstantiated causal claims leading to an extreme outcome.
- "circular_reasoning": Using the conclusion as a premise (check the graph structure). REQUIRES: The same claim appears as both evidence and conclusion.
- "appeal_to_emotion": Using emotional manipulation INSTEAD of logical argument. REQUIRES: The ENTIRE argument relies on emotion with NO logical substance. Mentioning real-world impacts or human consequences is NOT this fallacy.
- "goal_post_moving": Changing success criteria after they've been met.
- "red_herring": Introducing a clearly irrelevant topic to divert attention from the actual question.
- "appeal_to_authority": Citing an authority as SOLE evidence when the authority is not relevant or is being misused. Simply mentioning studies, experts, or data is NOT this fallacy — that's normal evidence.
- "hasty_generalization": Drawing a sweeping conclusion from clearly insufficient evidence. REQUIRES: An explicit generalization from a single anecdote or tiny sample. General policy claims based on economic reasoning are NOT hasty generalizations. Citing broad trends is NOT a hasty generalization.
- "tu_quoque": Deflecting criticism SOLELY by pointing to the other's behavior, without addressing the original point.
- "equivocation": Using a word with multiple meanings ambiguously in the same argument.

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
- ONLY flag fallacies with severity >= 0.5 — skip anything borderline or weak
- Aim for QUALITY over QUANTITY: flag 0-3 fallacies per batch of claims. If you're flagging more than 3, reconsider whether each one is truly a clear logical error
- Standard political rhetoric (citing economic data, referencing opponent's record, making policy predictions) are NOT fallacies
- Provide specific, actionable explanations
- Socratic questions should guide critical thinking, not be accusatory
- If no fallacies found, return {{"fallacies": []}}
- When in doubt, DO NOT flag it — err on the side of fewer, higher-quality detections"""

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
