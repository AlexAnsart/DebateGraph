"""
Skeptic Agent (Fallacy Hunter)
Detects logical fallacies using structural analysis + LLM.
Uses configurable prompts from config/settings.py.
"""

import os
import json
import asyncio
import logging
from typing import Optional

from api.models.schemas import (
    FallacyAnnotation,
    FallacyType,
    Claim,
    ClaimType,
)
from graph.store import DebateGraphStore
from graph.algorithms import detect_cycles, detect_strawman_candidates, detect_goalpost_moving
from config.settings import (
    LLM_MODEL,
    LLM_MODEL_FALLBACK,
    LLM_MAX_TOKENS_FALLACY,
    LLM_TEMPERATURE,
    CHUNK_SIZE,
    MAX_CONCURRENT_LLM_CALLS,
    SKEPTIC_SYSTEM_PROMPT,
    SKEPTIC_DETECTION_PROMPT,
)

logger = logging.getLogger("debategraph.skeptic")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class SkepticAgent:
    """
    Detects logical fallacies in the argument graph using a combination
    of structural analysis and LLM-based detection.
    """

    def __init__(self):
        self.client = None
        self.model = LLM_MODEL
        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
                logger.info(f"Skeptic Agent initialized with model: {self.model}")

    async def analyze(self, graph_store: DebateGraphStore) -> list[FallacyAnnotation]:
        """
        Run fallacy detection on the entire graph.
        Combines structural detection with LLM analysis.
        """
        all_fallacies: list[FallacyAnnotation] = []

        # 1. Structural detection (always runs, no API needed)
        structural = self._detect_structural_fallacies(graph_store)
        all_fallacies.extend(structural)
        logger.info(f"Structural detection found {len(structural)} fallacies")

        # 2. LLM-based detection
        if self.client:
            llm_fallacies = await self._detect_with_llm(graph_store)
            existing = {(f.claim_id, f.fallacy_type) for f in all_fallacies}
            for f in llm_fallacies:
                if (f.claim_id, f.fallacy_type) not in existing:
                    all_fallacies.append(f)
            logger.info(f"LLM detection found {len(llm_fallacies)} additional fallacies")
        else:
            rule_based = self._detect_rule_based(graph_store)
            existing = {(f.claim_id, f.fallacy_type) for f in all_fallacies}
            for f in rule_based:
                if (f.claim_id, f.fallacy_type) not in existing:
                    all_fallacies.append(f)

        # Add all fallacies to the graph store
        for fallacy in all_fallacies:
            graph_store.add_fallacy(fallacy)

        logger.info(f"Total fallacies detected: {len(all_fallacies)}")
        for f in all_fallacies:
            logger.info(f"  [{f.claim_id}] {f.fallacy_type.value} (severity={f.severity:.2f}): {f.explanation[:80]}...")

        return all_fallacies

    def _detect_structural_fallacies(
        self, graph_store: DebateGraphStore
    ) -> list[FallacyAnnotation]:
        """Detect fallacies from graph structure (no LLM needed)."""
        fallacies = []

        cycles = detect_cycles(graph_store.graph)
        for cycle in cycles:
            if len(cycle) >= 2:
                fallacies.append(FallacyAnnotation(
                    claim_id=cycle[0],
                    fallacy_type=FallacyType.CIRCULAR_REASONING,
                    severity=0.7,
                    explanation=f"Circular reasoning: claims {' → '.join(cycle)} form a logical loop.",
                    socratic_question="Can any of these claims stand on its own without relying on the others?",
                    related_claim_ids=cycle[1:],
                ))

        strawman_candidates = detect_strawman_candidates(graph_store.graph)
        for candidate in strawman_candidates:
            fallacies.append(FallacyAnnotation(
                claim_id=candidate["attacking_claim_id"],
                fallacy_type=FallacyType.STRAWMAN,
                severity=0.5,
                explanation=(
                    f"{candidate['attacker']} attacks {candidate['original_speaker']}'s claim, "
                    f"but may be misrepresenting the original argument."
                ),
                socratic_question="Does this response accurately address what the other speaker actually said?",
                related_claim_ids=[candidate["original_claim_id"]],
            ))

        goalpost_shifts = detect_goalpost_moving(graph_store.graph)
        for shift in goalpost_shifts:
            fallacies.append(FallacyAnnotation(
                claim_id=shift["original_claim_id"],
                fallacy_type=FallacyType.GOAL_POST_MOVING,
                severity=0.6,
                explanation=(
                    f"{shift['speaker']}'s original claim was challenged but they shifted "
                    f"to new claims without conceding the original point."
                ),
                socratic_question="Has the speaker acknowledged the challenge to their original claim?",
                related_claim_ids=[
                    sc["claim_id"] for sc in shift.get("subsequent_claims", [])
                ],
            ))

        return fallacies

    async def _detect_with_llm(
        self, graph_store: DebateGraphStore
    ) -> list[FallacyAnnotation]:
        """Detect fallacies using Claude API. Processes in chunks if many claims."""
        claims = graph_store.get_all_claims()
        if not claims:
            return []

        # Process in chunks if too many claims
        if len(claims) <= 15:
            return await self._detect_chunk(claims, graph_store)
        
        all_fallacies = []
        chunks = [claims[i:i+15] for i in range(0, len(claims), 15)]
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        
        async def process_chunk(chunk):
            async with semaphore:
                return await self._detect_chunk(chunk, graph_store)
        
        results = await asyncio.gather(*[process_chunk(c) for c in chunks])
        for result in results:
            all_fallacies.extend(result)
        
        return all_fallacies

    async def _detect_chunk(
        self, claims: list[Claim], graph_store: DebateGraphStore
    ) -> list[FallacyAnnotation]:
        """Detect fallacies in a chunk of claims."""
        context_parts = []
        for claim in claims:
            relations_str = ""
            for src, tgt, data in graph_store.graph.edges(data=True):
                if src == claim.id:
                    relations_str += f" --[{data.get('relation_type', '?')}]--> {tgt}"
                elif tgt == claim.id:
                    relations_str += f" <--[{data.get('relation_type', '?')}]-- {src}"

            context_parts.append(
                f"[{claim.id}] {claim.speaker} ({claim.claim_type.value}, "
                f"{'factual' if claim.is_factual else 'opinion'}): "
                f'"{claim.text}"{relations_str}'
            )

        claims_context = "\n".join(context_parts)

        try:
            message = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=LLM_MAX_TOKENS_FALLACY,
                temperature=LLM_TEMPERATURE,
                system=SKEPTIC_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": SKEPTIC_DETECTION_PROMPT.format(
                            claims_context=claims_context
                        ),
                    }
                ],
            )

            response_text = message.content[0].text
            logger.debug(f"Skeptic LLM response:\n{response_text[:1000]}...")

            json_str = self._extract_json(response_text)
            data = json.loads(json_str)

            fallacies = []
            valid_claim_ids = {c.id for c in claims}
            
            for f_data in data.get("fallacies", []):
                try:
                    claim_id = f_data["claim_id"]
                    if claim_id not in valid_claim_ids:
                        logger.warning(f"Skeptic: claim_id '{claim_id}' not found, skipping")
                        continue
                    
                    fallacy_type_str = f_data["fallacy_type"]
                    # Handle potential type mismatches
                    try:
                        fallacy_type = FallacyType(fallacy_type_str)
                    except ValueError:
                        logger.warning(f"Unknown fallacy type: {fallacy_type_str}")
                        continue
                    
                    fallacies.append(FallacyAnnotation(
                        claim_id=claim_id,
                        fallacy_type=fallacy_type,
                        severity=min(1.0, max(0.0, float(f_data.get("severity", 0.5)))),
                        explanation=f_data.get("explanation", ""),
                        socratic_question=f_data.get("socratic_question", ""),
                        related_claim_ids=[
                            rid for rid in f_data.get("related_claim_ids", [])
                            if rid in valid_claim_ids
                        ],
                    ))
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping invalid fallacy data: {e}")

            return fallacies

        except Exception as e:
            logger.error(f"LLM fallacy detection failed: {e}")
            return []

    def _detect_rule_based(
        self, graph_store: DebateGraphStore
    ) -> list[FallacyAnnotation]:
        """Rule-based fallacy detection fallback."""
        fallacies = []
        claims = graph_store.get_all_claims()

        for claim in claims:
            text_lower = claim.text.lower()

            # Ad Hominem
            ad_hominem_markers = [
                "you always", "you never", "people like you",
                "you're just", "you don't understand",
                "you're not qualified", "what do you know about",
            ]
            if any(m in text_lower for m in ad_hominem_markers):
                fallacies.append(FallacyAnnotation(
                    claim_id=claim.id,
                    fallacy_type=FallacyType.AD_HOMINEM,
                    severity=0.6,
                    explanation="This statement appears to attack the person rather than their argument.",
                    socratic_question="Is this criticism directed at the argument itself, or at the person making it?",
                ))

            # False Dilemma
            false_dilemma_markers = [
                "either we", "either you", "it's either",
                "the only option", "there are only two",
                "you're either with", "it's all or nothing",
            ]
            if any(m in text_lower for m in false_dilemma_markers):
                fallacies.append(FallacyAnnotation(
                    claim_id=claim.id,
                    fallacy_type=FallacyType.FALSE_DILEMMA,
                    severity=0.6,
                    explanation="This presents a binary choice where more options may exist.",
                    socratic_question="Are these really the only two options?",
                ))

            # Slippery Slope
            slippery_markers = [
                "will lead to", "will inevitably", "will end up",
                "next thing you know", "before you know it",
            ]
            if any(m in text_lower for m in slippery_markers):
                fallacies.append(FallacyAnnotation(
                    claim_id=claim.id,
                    fallacy_type=FallacyType.SLIPPERY_SLOPE,
                    severity=0.5,
                    explanation="This suggests an inevitable chain of consequences without justification.",
                    socratic_question="Is each step in this chain actually inevitable?",
                ))

            # Strawman (text-based)
            strawman_markers = [
                "so you're saying", "what you're really saying",
                "you're suggesting that", "you want to",
            ]
            if any(m in text_lower for m in strawman_markers):
                fallacies.append(FallacyAnnotation(
                    claim_id=claim.id,
                    fallacy_type=FallacyType.STRAWMAN,
                    severity=0.6,
                    explanation="This may be mischaracterizing the opponent's actual position.",
                    socratic_question="Is this an accurate representation of what the other speaker argued?",
                ))

        return fallacies

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response."""
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return text[start:end].strip()

        depth = 0
        start_idx = None
        for i, char in enumerate(text):
            if char == "{":
                if depth == 0:
                    start_idx = i
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start_idx is not None:
                    return text[start_idx:i + 1]

        return text
