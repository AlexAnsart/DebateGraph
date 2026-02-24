"""
Researcher Agent (Fact-Checker)
Uses Tavily web search API to verify factual claims,
then uses Claude to synthesize a verdict from search results.
"""

import os
import json
import asyncio
import logging
from typing import Optional

from api.models.schemas import (
    FactCheckResult,
    FactCheckVerdict,
    Claim,
)
from graph.store import DebateGraphStore
from config.settings import (
    LLM_MODEL,
    LLM_MAX_TOKENS_FACTCHECK,
    LLM_TEMPERATURE,
    MAX_CONCURRENT_LLM_CALLS,
    TAVILY_SEARCH_DEPTH,
    TAVILY_MAX_RESULTS,
    RESEARCHER_SYSTEM_PROMPT,
    RESEARCHER_VERDICT_PROMPT,
)

logger = logging.getLogger("debategraph.researcher")

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    logger.info("Tavily not installed. Fact-checking will use mock results.")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class ResearcherAgent:
    """
    Asynchronous fact-checking agent.
    For each factual claim:
    1. Searches the web via Tavily
    2. Uses Claude to synthesize a verdict from search results
    """

    def __init__(self):
        self.tavily_client = None
        self.llm_client = None
        
        if TAVILY_AVAILABLE:
            api_key = os.getenv("TAVILY_API_KEY", "")
            if api_key:
                self.tavily_client = TavilyClient(api_key=api_key)
                logger.info("Researcher Agent: Tavily API configured")
            else:
                logger.info("TAVILY_API_KEY not set. Using mock fact-checking.")
        
        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                self.llm_client = anthropic.Anthropic(api_key=api_key)
                logger.info("Researcher Agent: Claude API configured for verdict synthesis")

    async def check_all_factual_claims(
        self, graph_store: DebateGraphStore
    ) -> list[FactCheckResult]:
        """Fact-check all factual claims in the graph, with concurrency."""
        claims = graph_store.get_all_claims()
        factual_claims = [c for c in claims if c.is_factual]

        if not factual_claims:
            logger.info("No factual claims to check")
            return []

        logger.info(f"Fact-checking {len(factual_claims)} factual claims...")

        # Process with concurrency limit
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        
        async def check_with_semaphore(claim):
            async with semaphore:
                return await self.check_claim(claim)
        
        results = await asyncio.gather(
            *[check_with_semaphore(c) for c in factual_claims],
            return_exceptions=True,
        )

        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Fact-check failed for {factual_claims[i].id}: {result}")
                result = FactCheckResult(
                    claim_id=factual_claims[i].id,
                    verdict=FactCheckVerdict.UNVERIFIABLE,
                    confidence=0.0,
                    explanation=f"Fact-check error: {str(result)}",
                )
            graph_store.add_factcheck(result)
            valid_results.append(result)
            
            logger.info(
                f"  [{result.claim_id}] {result.verdict.value} "
                f"(confidence={result.confidence:.2f}): {result.explanation[:80]}..."
            )

        return valid_results

    async def check_claim(self, claim: Claim) -> FactCheckResult:
        """Fact-check a single claim."""
        if self.tavily_client:
            return await self._check_with_tavily(claim)
        else:
            return self._mock_factcheck(claim)

    async def _check_with_tavily(self, claim: Claim) -> FactCheckResult:
        """Fact-check using Tavily web search + optional LLM verdict."""
        try:
            # Step 1: Search the web
            query = f"fact check: {claim.text}"
            logger.debug(f"Tavily search: {query}")

            response = await asyncio.to_thread(
                self.tavily_client.search,
                query=query,
                search_depth=TAVILY_SEARCH_DEPTH,
                max_results=TAVILY_MAX_RESULTS,
                include_answer=True,
            )

            sources = [
                result.get("url", "")
                for result in response.get("results", [])
                if result.get("url")
            ]
            
            tavily_answer = response.get("answer", "")
            
            # Format search results for LLM
            search_results_text = ""
            for i, result in enumerate(response.get("results", [])[:5]):
                search_results_text += (
                    f"\n[Source {i+1}] {result.get('title', 'N/A')}\n"
                    f"URL: {result.get('url', 'N/A')}\n"
                    f"Content: {result.get('content', 'N/A')[:300]}\n"
                )
            
            if tavily_answer:
                search_results_text += f"\nTavily AI Summary: {tavily_answer}\n"

            # Step 2: Use LLM to synthesize verdict (if available)
            if self.llm_client and search_results_text.strip():
                return await self._synthesize_verdict(claim, search_results_text, sources)
            
            # Fallback: use Tavily's answer directly
            return self._verdict_from_tavily_answer(claim, tavily_answer, sources)

        except Exception as e:
            logger.error(f"Tavily fact-check failed for claim {claim.id}: {e}")
            return FactCheckResult(
                claim_id=claim.id,
                verdict=FactCheckVerdict.UNVERIFIABLE,
                confidence=0.0,
                explanation=f"Fact-check failed: {str(e)}",
            )

    async def _synthesize_verdict(
        self, claim: Claim, search_results: str, sources: list[str]
    ) -> FactCheckResult:
        """Use Claude to synthesize a verdict from search results."""
        try:
            message = await asyncio.to_thread(
                self.llm_client.messages.create,
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS_FACTCHECK,
                temperature=LLM_TEMPERATURE,
                system=RESEARCHER_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": RESEARCHER_VERDICT_PROMPT.format(
                            claim_text=claim.text,
                            speaker=claim.speaker,
                            search_results=search_results,
                        ),
                    }
                ],
            )

            response_text = message.content[0].text
            data = self._safe_parse_json(response_text)

            verdict_str = data.get("verdict", "unverifiable")
            try:
                verdict = FactCheckVerdict(verdict_str)
            except ValueError:
                verdict = FactCheckVerdict.UNVERIFIABLE

            return FactCheckResult(
                claim_id=claim.id,
                verdict=verdict,
                confidence=min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                sources=sources[:5],
                explanation=data.get("explanation", data.get("key_finding", "")),
            )

        except Exception as e:
            logger.error(f"LLM verdict synthesis failed: {e}")
            return self._verdict_from_tavily_answer(claim, "", sources)

    def _verdict_from_tavily_answer(
        self, claim: Claim, answer: str, sources: list[str]
    ) -> FactCheckResult:
        """Determine verdict from Tavily's answer without LLM."""
        answer_lower = answer.lower()

        if any(w in answer_lower for w in ["true", "correct", "confirmed", "accurate", "supported"]):
            verdict = FactCheckVerdict.SUPPORTED
            confidence = 0.65
        elif any(w in answer_lower for w in ["false", "incorrect", "debunked", "refuted", "wrong"]):
            verdict = FactCheckVerdict.REFUTED
            confidence = 0.65
        elif any(w in answer_lower for w in ["partially", "mixed", "nuanced", "somewhat"]):
            verdict = FactCheckVerdict.PARTIALLY_TRUE
            confidence = 0.5
        else:
            verdict = FactCheckVerdict.UNVERIFIABLE
            confidence = 0.3

        return FactCheckResult(
            claim_id=claim.id,
            verdict=verdict,
            confidence=confidence,
            sources=sources[:5],
            explanation=answer if answer else "Could not determine verdict from search results.",
        )

    def _mock_factcheck(self, claim: Claim) -> FactCheckResult:
        """Mock fact-checking for when no APIs are available."""
        return FactCheckResult(
            claim_id=claim.id,
            verdict=FactCheckVerdict.UNVERIFIABLE,
            confidence=0.3,
            explanation="No fact-checking API configured. Enable Tavily for real fact-checking.",
        )

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks robustly."""
        if "```json" in text:
            start = text.index("```json") + 7
            closing = text.find("```", start)
            if closing != -1:
                return text[start:closing].strip()
            else:
                remaining = text[start:].strip()
                return self._find_json_object(remaining)
        elif "```" in text:
            start = text.index("```") + 3
            newline = text.find("\n", start)
            if newline != -1 and newline - start < 20:
                start = newline + 1
            closing = text.find("```", start)
            if closing != -1:
                return text[start:closing].strip()
            else:
                remaining = text[start:].strip()
                return self._find_json_object(remaining)

        return self._find_json_object(text)

    def _safe_parse_json(self, text: str) -> dict:
        """Parse JSON with fallback repair for common LLM JSON errors."""
        import re
        json_str = self._extract_json(text)
        
        # First try direct parse
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # Try to repair: replace unescaped apostrophes inside string values
        # This handles cases like "explanation": "it's a problem"
        try:
            # Replace smart quotes
            repaired = json_str.replace('\u2019', "'").replace('\u2018', "'")
            repaired = repaired.replace('\u201c', '"').replace('\u201d', '"')
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
        
        # Last resort: try to extract just the verdict/confidence/explanation fields
        try:
            verdict_match = re.search(r'"verdict"\s*:\s*"([^"]+)"', json_str)
            confidence_match = re.search(r'"confidence"\s*:\s*([\d.]+)', json_str)
            explanation_match = re.search(r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)"', json_str)
            
            if verdict_match:
                return {
                    "verdict": verdict_match.group(1),
                    "confidence": float(confidence_match.group(1)) if confidence_match else 0.5,
                    "explanation": explanation_match.group(1) if explanation_match else "",
                }
        except Exception:
            pass
        
        raise json.JSONDecodeError("Could not parse JSON", json_str, 0)

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

        if start_idx is not None:
            return text[start_idx:]

        return text
