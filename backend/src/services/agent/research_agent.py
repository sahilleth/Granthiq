"""
Multi-step research agent for deep document analysis.

Pipeline: Plan → Search (per sub-query) → Synthesize with citations.
Streams agent step events alongside the final answer.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

from loguru import logger
from pydantic import BaseModel, Field
from llama_index.core.program import LLMTextCompletionProgram

from src.config import get_settings
from src.services.llm.factory import create_llamaindex_llm
from src.services.llm.provider_selector import select_chat_llm_provider
from src.services.query.query_engine import QueryEngineService
from src.services.query.response_utils import (
    compute_confidence_metadata,
    extract_citations_from_sources,
    get_sources_from_response,
)
from src.utils.output_parsers import RobustJSONParser


class ResearchPlan(BaseModel):
    """Decomposed research plan from the user's question."""

    reasoning: str = Field(description="Brief explanation of the research approach")
    sub_queries: List[str] = Field(
        description="2-4 focused sub-queries to search the document corpus",
        min_length=1,
        max_length=5,
    )


class ResearchAgentService:
    """
    Agentic RAG pipeline that plans, searches iteratively, and synthesizes.

    Unlike single-shot RAG, this decomposes complex questions into sub-queries,
    retrieves context for each, then produces a cited synthesis.
    """

    MAX_SUB_QUERIES = 4
    MAX_CONTEXT_CHARS = 12000

    def __init__(self) -> None:
        self.settings = get_settings()

    def _create_llm(self):
        provider = select_chat_llm_provider(self.settings)
        api_key = getattr(self.settings.llm, f"{provider}_api_key", None)
        model_map = {
            "groq": "llama-3.3-70b-versatile",
            "gemini": "gemini-2.5-flash",
            "openai": self.settings.llm.model_name,
        }
        return create_llamaindex_llm(
            provider=provider,
            api_key=api_key,
            model=model_map.get(provider, "gemini-2.5-flash"),
            temperature=0.4,
            max_tokens=4096,
        )

    def _step_event(self, step_id: int, action: str, status: str, detail: str, **extra) -> str:
        payload = {
            "type": "agent_step",
            "step": {
                "id": step_id,
                "action": action,
                "status": status,
                "detail": detail,
                **extra,
            },
        }
        return json.dumps(payload)

    async def _plan(self, question: str, llm) -> ResearchPlan:
        program = LLMTextCompletionProgram.from_defaults(
            output_parser=RobustJSONParser(output_cls=ResearchPlan),
            prompt_template_str=(
                "You are a research planning agent. Decompose the user's question into "
                "2-4 focused sub-queries that can be answered by searching a document corpus.\n\n"
                "User question: {question}\n\n"
                "Return JSON with:\n"
                '- "reasoning": one sentence on your approach\n'
                '- "sub_queries": array of 2-4 specific search queries\n'
            ),
            llm=llm,
        )
        plan = await program.acall(question=question)
        plan.sub_queries = plan.sub_queries[: self.MAX_SUB_QUERIES]
        return plan

    def _dedupe_sources(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        unique: List[Dict[str, Any]] = []
        for src in sources:
            text_key = (src.get("text") or "")[:120]
            doc_id = src.get("metadata", {}).get("document_id", "")
            key = f"{doc_id}:{text_key}"
            if key not in seen:
                seen.add(key)
                unique.append(src)
        return unique

    def _build_synthesis_context(self, sources: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        total = 0
        for i, src in enumerate(sources, 1):
            text = src.get("text", "")
            meta = src.get("metadata", {})
            if "metadata" in meta and isinstance(meta["metadata"], dict):
                meta = meta["metadata"]
            filename = meta.get("filename", "Unknown")
            page = meta.get("page_number")
            page_str = f", p.{page}" if page else ""
            chunk = f"[Source {i}: {filename}{page_str}]\n{text}\n"
            if total + len(chunk) > self.MAX_CONTEXT_CHARS:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n---\n".join(parts)

    async def run(
        self,
        question: str,
        query_engine: QueryEngineService,
        filters: Optional[Dict[str, Any]],
        user_id: UUID,
        notebook_id: UUID,
        min_score_threshold: float = 0.10,
    ) -> AsyncIterator[str]:
        """
        Execute the research agent pipeline, yielding SSE-compatible events.

        Yields:
            - JSON agent_step events
            - Text tokens (final synthesis)
            - JSON metadata event with citations + confidence
        """
        llm = self._create_llm()
        step_id = 0

        # --- Step 1: Plan ---
        step_id += 1
        yield self._step_event(step_id, "plan", "running", "Analyzing question and planning research steps...")
        try:
            plan = await self._plan(question, llm)
            sub_queries = plan.sub_queries or [question]
            yield self._step_event(
                step_id,
                "plan",
                "complete",
                plan.reasoning,
                sub_queries=sub_queries,
            )
        except Exception as e:
            logger.warning(f"Research plan failed, using original question: {e}")
            sub_queries = [question]
            yield self._step_event(
                step_id, "plan", "complete", "Using direct search approach.", sub_queries=sub_queries
            )

        # --- Step 2: Search ---
        all_sources: List[Dict[str, Any]] = []
        for i, sub_q in enumerate(sub_queries, 1):
            step_id += 1
            yield self._step_event(
                step_id,
                "search",
                "running",
                f"Searching documents ({i}/{len(sub_queries)}): {sub_q[:80]}...",
                sub_query=sub_q,
            )
            try:
                response = await query_engine.aquery(
                    query_str=sub_q,
                    filters=filters,
                    user_id=str(user_id),
                    session_id=str(notebook_id),
                )
                sources = get_sources_from_response(response)
                all_sources.extend(sources)
                yield self._step_event(
                    step_id,
                    "search",
                    "complete",
                    f"Found {len(sources)} relevant passages",
                    results_count=len(sources),
                    sub_query=sub_q,
                )
            except Exception as e:
                logger.error(f"Research search failed for '{sub_q}': {e}")
                yield self._step_event(
                    step_id, "search", "complete", f"Search encountered an issue: {e}", results_count=0
                )

        deduped = self._dedupe_sources(all_sources)

        # --- Step 3: Synthesize ---
        step_id += 1
        yield self._step_event(
            step_id,
            "synthesize",
            "running",
            f"Synthesizing answer from {len(deduped)} sources...",
            source_count=len(deduped),
        )

        if not deduped:
            refusal = (
                "I couldn't find sufficient relevant information in your documents to "
                "answer this research question. Try adding more sources or rephrasing."
            )
            yield refusal
            confidence = compute_confidence_metadata([], min_score_threshold)
            yield json.dumps({"type": "metadata", "citations": [], "confidence": confidence})
            return

        context = self._build_synthesis_context(deduped)
        synthesis_prompt = (
            "You are a research assistant synthesizing findings from multiple document searches.\n"
            "Write a thorough, well-structured answer to the user's question.\n"
            "Cite sources inline using [1], [2], etc. matching the source numbers below.\n"
            "If evidence is weak or conflicting, say so explicitly.\n\n"
            f"User question: {question}\n\n"
            f"Retrieved sources:\n{context}\n\n"
            "Answer:"
        )

        response = await llm.astream_complete(synthesis_prompt)
        async for chunk in response:
            delta = chunk.delta if hasattr(chunk, "delta") else str(chunk)
            if delta:
                yield delta

        yield self._step_event(step_id, "synthesize", "complete", "Research synthesis complete.")

        citations_raw = extract_citations_from_sources(deduped)
        confidence = compute_confidence_metadata(deduped, min_score_threshold)
        yield json.dumps(
            {
                "type": "metadata",
                "_sources_for_save": deduped,
                "confidence": confidence,
            }
        )
