"""
Ontological Agent (Structural Agent)
Responsible for:
- Converting transcription segments into typed Claims
- Identifying claim types (premise, conclusion, concession, rebuttal)
- Inferring relations between claims
- Tagging claims as factual vs opinion
- Building the argument graph topology

Uses Claude API with configurable prompts from config/settings.py.
Falls back to rule-based extraction if the API is unavailable.
"""

import os
import json
import time
import uuid
import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from api.models.schemas import (
    Claim,
    ClaimRelation,
    ClaimType,
    EdgeType,
    TranscriptionResult,
    TranscriptionSegment,
)
from graph.store import DebateGraphStore
from config.settings import (
    LLM_MODEL,
    LLM_MODEL_FALLBACK,
    LLM_MAX_TOKENS_EXTRACTION,
    LLM_TEMPERATURE,
    CHUNK_SIZE,
    MAX_CONCURRENT_LLM_CALLS,
    ONTOLOGICAL_SYSTEM_PROMPT,
    ONTOLOGICAL_EXTRACTION_PROMPT,
)

if TYPE_CHECKING:
    from session_log.session_structured_logger import SessionLogger

logger = logging.getLogger("debategraph.ontological")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Using rule-based extraction.")


class OntologicalAgent:
    """
    Extracts claims and builds the argument graph structure
    from transcription segments. Processes in chunks for efficiency.
    """

    def __init__(self, session_logger: Optional["SessionLogger"] = None):
        self.client = None
        self.model = LLM_MODEL
        self._session_logger = session_logger
        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
                logger.info(f"Ontological Agent initialized with model: {self.model}")
            else:
                logger.warning("ANTHROPIC_API_KEY not set. Using rule-based extraction.")

    async def extract_and_build(
        self,
        transcription: TranscriptionResult,
        graph_store: DebateGraphStore,
    ) -> None:
        """
        Main entry point: extract claims from transcription and build the graph.
        Processes segments in chunks for parallel LLM calls.
        """
        if self.client:
            await self._extract_with_llm_chunked(transcription, graph_store)
        else:
            self._extract_rule_based(transcription, graph_store)

        logger.info(
            f"Graph built: {graph_store.num_nodes} nodes, {graph_store.num_edges} edges"
        )

    def _filter_segments(self, segments: list) -> list:
        """Filter out noise segments (single words, fillers, very short fragments)."""
        FILLER_WORDS = {
            "uh", "um", "ah", "oh", "okay", "ok", "yeah", "yes", "no", "well",
            "so", "and", "but", "the", "a", "i", "he", "she", "it", "we", "you",
            "actually", "look", "now", "right", "fine", "sure", "good", "great",
            "settled", "alright", "anyway", "indeed", "exactly", "absolutely",
        }
        filtered = []
        for seg in segments:
            text = seg.text.strip()
            words = text.split()
            # Skip very short segments (< 4 words) that are just fillers
            if len(words) < 4:
                text_lower = text.lower().rstrip('.,!?')
                if text_lower in FILLER_WORDS or len(text) < 10:
                    continue
            filtered.append(seg)
        
        skipped = len(segments) - len(filtered)
        if skipped > 0:
            logger.info(f"Filtered {skipped} noise segments (kept {len(filtered)}/{len(segments)})")
        return filtered

    async def _extract_with_llm_chunked(
        self,
        transcription: TranscriptionResult,
        graph_store: DebateGraphStore,
    ) -> None:
        """Extract claims using Claude API, processing in parallel chunks."""
        # Filter noise segments before processing
        segments = self._filter_segments(transcription.segments)
        
        if len(segments) <= CHUNK_SIZE:
            # Small enough to process in one call
            await self._extract_chunk(segments, graph_store, chunk_idx=0)
            return

        # Split into chunks
        chunks = []
        for i in range(0, len(segments), CHUNK_SIZE):
            chunks.append(segments[i:i + CHUNK_SIZE])
        
        logger.info(f"Processing {len(segments)} segments in {len(chunks)} chunks "
                     f"(chunk_size={CHUNK_SIZE}, max_concurrent={MAX_CONCURRENT_LLM_CALLS})")

        # Process chunks with concurrency limit
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        
        async def process_with_semaphore(chunk, idx):
            async with semaphore:
                return await self._extract_chunk(chunk, graph_store, chunk_idx=idx)
        
        tasks = [
            process_with_semaphore(chunk, idx)
            for idx, chunk in enumerate(chunks)
        ]
        
        await asyncio.gather(*tasks)
        
        # After all chunks, do a relation-linking pass across chunks
        if len(chunks) > 1:
            await self._link_cross_chunk_relations(graph_store)

    async def _extract_chunk(
        self,
        segments: list[TranscriptionSegment],
        graph_store: DebateGraphStore,
        chunk_idx: int = 0,
    ) -> None:
        """Extract claims from a chunk of segments using Claude API."""
        transcript_text = self._format_segments(segments)
        
        logger.info(f"[Chunk {chunk_idx}] Extracting claims from {len(segments)} segments...")
        logger.debug(f"[Chunk {chunk_idx}] Transcript:\n{transcript_text[:500]}...")

        source_tag = f"ontological_chunk_{chunk_idx}"
        try:
            t0 = time.perf_counter()
            message = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=LLM_MAX_TOKENS_EXTRACTION,
                temperature=LLM_TEMPERATURE,
                system=ONTOLOGICAL_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": ONTOLOGICAL_EXTRACTION_PROMPT.format(
                            transcription=transcript_text
                        ),
                    }
                ],
            )
            duration = time.perf_counter() - t0
            response_text = message.content[0].text
            logger.debug(f"[Chunk {chunk_idx}] Raw LLM response:\n{response_text[:1000]}...")

            if self._session_logger:
                usage = None
                if getattr(message, "usage", None):
                    usage = {"input_tokens": getattr(message.usage, "input_tokens", None), "output_tokens": getattr(message.usage, "output_tokens", None)}
                self._session_logger.log_llm_call(
                    provider="anthropic",
                    model=self.model,
                    role="ontological_extraction",
                    system_prompt=ONTOLOGICAL_SYSTEM_PROMPT,
                    user_content=ONTOLOGICAL_EXTRACTION_PROMPT.format(transcription=transcript_text),
                    response_text=response_text,
                    usage=usage,
                    duration_seconds=round(duration, 3),
                    extra={"chunk_idx": chunk_idx},
                )

            json_str = self._extract_json(response_text)
            data = json.loads(json_str)

            claims_added = 0
            relations_added = 0

            for claim_data in data.get("claims", []):
                try:
                    # Prefix claim IDs with chunk index to avoid collisions
                    claim_id = claim_data.get("id", str(uuid.uuid4())[:8])
                    if chunk_idx > 0:
                        claim_id = f"ch{chunk_idx}_{claim_id}"
                    
                    claim = Claim(
                        id=claim_id,
                        speaker=claim_data["speaker"],
                        text=claim_data["text"],
                        claim_type=ClaimType(claim_data["claim_type"]),
                        timestamp_start=claim_data.get("timestamp_start", 0.0),
                        timestamp_end=claim_data.get("timestamp_end", 0.0),
                        confidence=claim_data.get("confidence", 0.8),
                        is_factual=claim_data.get("is_factual", False),
                    )
                    graph_store.add_claim(claim)
                    if self._session_logger:
                        self._session_logger.log_node_created(
                            node_id=claim.id,
                            claim_data=claim.model_dump(mode="json"),
                            source=source_tag,
                        )
                    claims_added += 1
                except (ValueError, KeyError) as e:
                    logger.warning(f"[Chunk {chunk_idx}] Skipping invalid claim: {e}")

            for rel_data in data.get("relations", []):
                try:
                    source_id = rel_data["source_id"]
                    target_id = rel_data["target_id"]
                    if chunk_idx > 0:
                        source_id = f"ch{chunk_idx}_{source_id}"
                        target_id = f"ch{chunk_idx}_{target_id}"
                    
                    relation = ClaimRelation(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type=EdgeType(rel_data["relation_type"]),
                        confidence=rel_data.get("confidence", 0.7),
                    )
                    graph_store.add_relation(relation)
                    if self._session_logger:
                        self._session_logger.log_edge_created(
                            source_id=source_id,
                            target_id=target_id,
                            relation_type=relation.relation_type.value,
                            confidence=relation.confidence,
                            source=source_tag,
                        )
                    relations_added += 1
                except (ValueError, KeyError) as e:
                    logger.warning(f"[Chunk {chunk_idx}] Skipping invalid relation: {e}")

            logger.info(f"[Chunk {chunk_idx}] Extracted {claims_added} claims, "
                        f"{relations_added} relations")

        except anthropic.APIError as e:
            logger.error(f"[Chunk {chunk_idx}] Claude API error: {e}")
            # Try fallback model
            if self.model != LLM_MODEL_FALLBACK:
                logger.info(f"[Chunk {chunk_idx}] Retrying with fallback model: {LLM_MODEL_FALLBACK}")
                old_model = self.model
                self.model = LLM_MODEL_FALLBACK
                try:
                    await self._extract_chunk(segments, graph_store, chunk_idx)
                finally:
                    self.model = old_model
            else:
                logger.error(f"[Chunk {chunk_idx}] Fallback also failed. Using rule-based.")
                self._extract_rule_based_segments(segments, graph_store, chunk_idx)
        except json.JSONDecodeError as e:
            logger.error(f"[Chunk {chunk_idx}] JSON parse error: {e}")
            self._extract_rule_based_segments(segments, graph_store, chunk_idx)
        except Exception as e:
            logger.error(f"[Chunk {chunk_idx}] Unexpected error: {e}", exc_info=True)
            self._extract_rule_based_segments(segments, graph_store, chunk_idx)

    async def _link_cross_chunk_relations(self, graph_store: DebateGraphStore) -> None:
        """After processing all chunks, link claims across chunk boundaries."""
        claims = graph_store.get_all_claims()
        if len(claims) < 2:
            return
        
        # Simple heuristic: link consecutive claims from different speakers
        sorted_claims = sorted(claims, key=lambda c: c.timestamp_start)
        
        cross_links = 0
        for i in range(1, len(sorted_claims)):
            prev = sorted_claims[i - 1]
            curr = sorted_claims[i]
            
            # Skip if already linked
            if graph_store.graph.has_edge(curr.id, prev.id) or graph_store.graph.has_edge(prev.id, curr.id):
                continue
            
            # Link cross-speaker responses
            if prev.speaker != curr.speaker:
                if curr.claim_type == ClaimType.REBUTTAL:
                    rel = ClaimRelation(
                        source_id=curr.id,
                        target_id=prev.id,
                        relation_type=EdgeType.ATTACK,
                        confidence=0.6,
                    )
                    graph_store.add_relation(rel)
                    if self._session_logger:
                        self._session_logger.log_edge_created(
                            source_id=rel.source_id,
                            target_id=rel.target_id,
                            relation_type=rel.relation_type.value,
                            confidence=rel.confidence,
                            source="cross_chunk_link",
                        )
                    cross_links += 1
        
        if cross_links > 0:
            logger.info(f"Added {cross_links} cross-chunk relations")

    def _extract_rule_based(
        self,
        transcription: TranscriptionResult,
        graph_store: DebateGraphStore,
    ) -> None:
        """Rule-based claim extraction fallback."""
        logger.info("Using rule-based claim extraction")
        self._extract_rule_based_segments(transcription.segments, graph_store, 0)

    def _extract_rule_based_segments(
        self,
        segments: list[TranscriptionSegment],
        graph_store: DebateGraphStore,
        chunk_idx: int,
    ) -> None:
        """Rule-based extraction for a list of segments."""
        source_tag = f"rule_based_chunk_{chunk_idx}"
        claims = []
        for i, segment in enumerate(segments):
            claim_type = self._infer_claim_type(segment.text)
            is_factual = self._is_factual_claim(segment.text)
            
            claim_id = f"c{chunk_idx}_{i + 1}" if chunk_idx > 0 else f"c{i + 1}"
            
            claim = Claim(
                id=claim_id,
                speaker=segment.speaker,
                text=segment.text,
                claim_type=claim_type,
                timestamp_start=segment.start,
                timestamp_end=segment.end,
                confidence=0.7,
                is_factual=is_factual,
            )
            claims.append(claim)
            graph_store.add_claim(claim)
            if self._session_logger:
                self._session_logger.log_node_created(
                    node_id=claim.id,
                    claim_data=claim.model_dump(mode="json"),
                    source=source_tag,
                )

        # Infer relations
        for i, claim in enumerate(claims):
            if i == 0:
                continue
            prev = claims[i - 1]
            if claim.speaker != prev.speaker:
                if claim.claim_type == ClaimType.REBUTTAL:
                    rel = ClaimRelation(
                        source_id=claim.id,
                        target_id=prev.id,
                        relation_type=EdgeType.ATTACK,
                        confidence=0.65,
                    )
                    graph_store.add_relation(rel)
                    if self._session_logger:
                        self._session_logger.log_edge_created(
                            source_id=rel.source_id,
                            target_id=rel.target_id,
                            relation_type=rel.relation_type.value,
                            confidence=rel.confidence,
                            source=source_tag,
                        )
                elif claim.claim_type == ClaimType.CONCESSION:
                    rel = ClaimRelation(
                        source_id=claim.id,
                        target_id=prev.id,
                        relation_type=EdgeType.SUPPORT,
                        confidence=0.5,
                    )
                    graph_store.add_relation(rel)
                    if self._session_logger:
                        self._session_logger.log_edge_created(
                            source_id=rel.source_id,
                            target_id=rel.target_id,
                            relation_type=rel.relation_type.value,
                            confidence=rel.confidence,
                            source=source_tag,
                        )
            elif claim.claim_type == ClaimType.PREMISE and prev.claim_type == ClaimType.CONCLUSION:
                rel = ClaimRelation(
                    source_id=claim.id,
                    target_id=prev.id,
                    relation_type=EdgeType.SUPPORT,
                    confidence=0.6,
                )
                graph_store.add_relation(rel)
                if self._session_logger:
                    self._session_logger.log_edge_created(
                        source_id=rel.source_id,
                        target_id=rel.target_id,
                        relation_type=rel.relation_type.value,
                        confidence=rel.confidence,
                        source=source_tag,
                    )

    def _infer_claim_type(self, text: str) -> ClaimType:
        """Infer claim type from text patterns."""
        text_lower = text.lower()
        
        concession_markers = ["i agree", "you're right", "that's true", "fair point",
                              "i concede", "granted", "even if", "although"]
        if any(m in text_lower for m in concession_markers):
            return ClaimType.CONCESSION

        rebuttal_markers = ["but that's", "however", "that's wrong", "that's not true",
                            "i disagree", "on the contrary", "that's false",
                            "you're misrepresenting", "that's misleading"]
        if any(m in text_lower for m in rebuttal_markers):
            return ClaimType.REBUTTAL

        conclusion_markers = ["therefore", "thus", "so we can conclude", "in conclusion",
                              "this means", "this shows", "this proves", "my position is"]
        if any(m in text_lower for m in conclusion_markers):
            return ClaimType.CONCLUSION

        return ClaimType.PREMISE

    def _is_factual_claim(self, text: str) -> bool:
        """Determine if a claim is factual (verifiable)."""
        text_lower = text.lower()
        factual_markers = ["study", "studies", "research", "data", "percent", "%",
                           "according to", "statistics", "evidence", "report",
                           "million", "billion", "number", "rate"]
        opinion_markers = ["i believe", "i think", "in my opinion", "i feel",
                           "should", "ought to"]
        
        factual_score = sum(1 for m in factual_markers if m in text_lower)
        opinion_score = sum(1 for m in opinion_markers if m in text_lower)
        return factual_score > opinion_score

    def _format_segments(self, segments: list[TranscriptionSegment]) -> str:
        """Format segments for the LLM prompt."""
        lines = []
        for i, seg in enumerate(segments):
            lines.append(
                f"[Segment {i}] [{seg.start:.1f}s - {seg.end:.1f}s] {seg.speaker}: {seg.text}"
            )
        return "\n".join(lines)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks robustly."""
        # Try ```json ... ``` blocks first
        if "```json" in text:
            start = text.index("```json") + 7
            # Find closing ``` — if not found, take everything after the opening
            closing = text.find("```", start)
            if closing != -1:
                return text[start:closing].strip()
            else:
                # No closing backticks — take rest of text and try to find JSON
                remaining = text[start:].strip()
                return self._find_json_object(remaining)
        elif "```" in text:
            start = text.index("```") + 3
            # Skip optional language identifier on same line
            newline = text.find("\n", start)
            if newline != -1 and newline - start < 20:
                start = newline + 1
            closing = text.find("```", start)
            if closing != -1:
                return text[start:closing].strip()
            else:
                remaining = text[start:].strip()
                return self._find_json_object(remaining)

        # No code blocks — find raw JSON object
        return self._find_json_object(text)

    def _find_json_object(self, text: str) -> str:
        """Find the first complete JSON object in text using brace matching."""
        depth = 0
        start_idx = None
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue

            if char == "{":
                if depth == 0:
                    start_idx = i
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start_idx is not None:
                    return text[start_idx:i + 1]

        # If we found an opening brace but no matching close, return from start to end
        if start_idx is not None:
            return text[start_idx:]

        return text
