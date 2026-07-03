from typing import List, Dict, Any, AsyncIterator, Union, Optional
from uuid import UUID
from loguru import logger
import json
import hashlib
import random
from datetime import datetime, timezone
from pydantic import BaseModel
from llama_index.core.program import LLMTextCompletionProgram
from src.utils.output_parsers import RobustJSONParser

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from langfuse import observe
from fastapi import HTTPException
from sqlalchemy import delete

from src.db.repositories.chat import ChatRepository
from src.db.repositories.notebook import NotebookRepository
from src.db.models import ChatMessage, MessageCitation, ChatRole
from src.services.query.query_engine import QueryEngineService
from src.config import get_settings
from src.services.query.response_utils import (
    get_sources_from_response,
    extract_citations_from_sources,
    enrich_citations_with_filenames,
    compute_confidence_metadata,
)
from src.services.observability.langfuse_config import get_langfuse_client
from src.db.session import async_session_factory
from src.utils.rag_config import merge_rag_settings, get_policy_overrides
from src.services.chat.filters import build_chat_filters
from src.services.llm.provider_selector import (
    select_chat_llm_provider,
    select_generation_llm_provider,
)
from src.services.llm.factory import create_llamaindex_llm
from src.constants import STREAMING_CHUNK_SIZE_CHARS
from src.db.vector_store import get_vector_store
from src.services.reranker.reranker import get_reranker
from src.db.repositories.document import DocumentRepository
from src.db.models import ProcessingStatus
from src.utils.request_dedup import get_deduplicator
from src.services.agent.research_agent import ResearchAgentService


_warmed_up = False


def warmup_heavy_components() -> None:
    """
    Pre-initialize heavy components to avoid latency on first request.

    This should be called during application startup (e.g., in app.py lifespan).
    The components are cached as singletons, so subsequent calls are no-ops.
    """
    global _warmed_up
    if _warmed_up:
        logger.debug("Heavy components already warmed up")
        return

    logger.info("Warming up heavy components (vector store, embeddings, BM42)...")

    try:
        # 1. Initialize vector store singleton (loads embeddings + BM42)

        vs = get_vector_store()
        logger.info(f"Vector store warmed up: collection={vs.collection_name}")

        # 2. Initialize reranker singleton

        reranker = get_reranker()
        if reranker:
            logger.info("Reranker warmed up")

        _warmed_up = True
        logger.info("Heavy components warmup complete")

    except Exception as e:
        logger.error(f"Failed to warmup heavy components: {e}", exc_info=True)
        # Don't fail the app - first request will just be slower


class SuggestionList(BaseModel):
    questions: List[str]


class SuggestionItem(BaseModel):
    text: str
    context: str = ""  # Made optional with default to handle truncated LLM output


class DocumentSuggestionList(BaseModel):
    items: List[SuggestionItem]


class ChatService:
    """
    Service for handling chat conversations.
    Manages chat history and integrates with RAG query engine.

    Per-notebook RAG settings are respected via merge_rag_settings().
    Heavy components (vector store, embeddings) are cached globally.
    """

    def __init__(self):
        self.settings = get_settings()

    def _setup_langfuse_trace(
        self, langfuse: Any, user_id: UUID, notebook_id: UUID
    ) -> None:
        """Setup Langfuse trace with user and session info."""
        if langfuse:
            langfuse.update_current_trace(
                user_id=str(user_id),
                session_id=str(notebook_id),
                metadata={"operation": "chat", "notebook_id": str(notebook_id)},
            )

    async def _validate_notebook_access(
        self, session: AsyncSession, notebook_id: UUID, user_id: UUID
    ) -> Any:
        """Validate notebook exists and user has access."""
        notebook_repo = NotebookRepository(session)
        notebook = await notebook_repo.get_notebook(notebook_id, user_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return notebook

    def _create_query_engine(self, notebook: Any, stream: bool) -> QueryEngineService:
        """Create query engine with merged notebook settings."""
        rag_settings = merge_rag_settings(notebook.settings, self.settings.rag)
        policy = get_policy_overrides(notebook.settings)
        chat_llm_provider = select_chat_llm_provider(self.settings)
        return QueryEngineService.from_rag_settings(
            rag_settings=rag_settings,
            stream=stream,
            llm_provider=chat_llm_provider,
            policy_min_score=policy.get("min_score_threshold"),
            policy_min_chunks=policy.get("min_context_chunks"),
        )

    def _get_min_score_threshold(self, notebook: Any) -> float:
        policy = get_policy_overrides(notebook.settings)
        return policy.get(
            "min_score_threshold", self.settings.policy.min_score_threshold
        )

    async def _save_user_message(
        self, chat_repo: ChatRepository, notebook_id: UUID, message: str
    ) -> None:
        """Save user message to database."""
        await chat_repo.add_message(
            notebook_id=notebook_id, role=ChatRole.USER, content=message
        )
        logger.info(f"Saved user message for notebook {notebook_id}")

    async def _handle_streaming_response(
        self,
        query_engine_service: QueryEngineService,
        message: str,
        filters: Any,
        user_id: UUID,
        notebook_id: UUID,
        langfuse: Any,
    ) -> AsyncIterator[str]:
        """Handle streaming response generation and saving."""

        async def _stream_generator():
            response_chunks = []
            sources = []

            async for token in query_engine_service.stream_query(
                query_str=message,
                filters=filters,
                user_id=str(user_id),
                session_id=str(notebook_id),
            ):
                # Debug: log tokens containing newlines
                if "\n" in token:
                    logger.info(f"Token with newline: {repr(token)}")
                response_chunks.append(token)
                yield token

            final_text = "".join(response_chunks)

            # Debug: Check what was actually streamed
            logger.info(f"Stream complete. Final text length: {len(final_text)}")
            logger.info(f"First 200 chars: {repr(final_text[:200])}")

            try:
                # Save response and get full object with citations
                async with async_session_factory() as save_session:
                    last_response = query_engine_service.get_last_response()
                    if last_response:
                        sources = get_sources_from_response(last_response)

                    saved_response = await self._save_assistant_response(
                        session=save_session,
                        notebook_id=notebook_id,
                        response_text=final_text,
                        sources=sources,
                        langfuse=langfuse,
                    )

                    # Yield the final payload with citations as a JSON string
                    # The frontend expects { "citations": [...] }
                    if "citations" in saved_response:
                        yield json.dumps({"citations": saved_response["citations"]})

            except Exception as save_error:
                logger.error(
                    f"Failed to save streaming message: {save_error}",
                    exc_info=True,
                )

        return _stream_generator()

    async def _handle_regular_response(
        self,
        query_engine_service: QueryEngineService,
        message: str,
        filters: Any,
        user_id: UUID,
        notebook_id: UUID,
        session: AsyncSession,
        langfuse: Any,
    ) -> Dict[str, Any]:
        """Handle regular (non-streaming) response."""
        response = await query_engine_service.aquery(
            query_str=message,
            filters=filters,
            user_id=str(user_id),
            session_id=str(notebook_id),
        )

        response_text = (
            response.response if hasattr(response, "response") else str(response)
        )
        sources = get_sources_from_response(response)

        return await self._save_assistant_response(
            session=session,
            notebook_id=notebook_id,
            response_text=response_text,
            sources=sources,
            langfuse=langfuse,
        )

    async def _handle_chat_error(
        self,
        e: Exception,
        chat_repo: ChatRepository,
        notebook_id: UUID,
        langfuse: Any,
    ) -> None:
        """Handle chat errors and save error message."""
        logger.error(f"Chat error for notebook {notebook_id}: {e}", exc_info=True)

        await chat_repo.add_message(
            notebook_id=notebook_id,
            role=ChatRole.ASSISTANT,
            content="Sorry, I encountered an error processing your request. Please try again.",
        )

        if langfuse:
            langfuse.update_current_trace(metadata={"error": str(e)})

        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")

    @observe(name="send_chat_message")
    async def send_message(
        self,
        session: AsyncSession,
        notebook_id: UUID,
        user_id: UUID,
        message: str,
        stream: bool = False,
        mode: str = "chat",
    ) -> Union[Dict[str, Any], AsyncIterator[str]]:
        """
        Process a user message and return assistant response.
        Saves both user and assistant messages to database with citations.

        Args:
            mode: "chat" for standard RAG, "research" for multi-step research agent

        Uses notebook-specific RAG settings merged with global defaults.
        Includes request deduplication to prevent duplicate LLM calls.
        """
        langfuse = get_langfuse_client()
        self._setup_langfuse_trace(langfuse, user_id, notebook_id)

        notebook = await self._validate_notebook_access(session, notebook_id, user_id)

        filters, _, warning_message = await build_chat_filters(notebook_id, session)
        if warning_message:
            logger.warning(warning_message)

        if mode == "research":
            return await self._send_research_message(
                session=session,
                notebook=notebook,
                notebook_id=notebook_id,
                user_id=user_id,
                message=message,
                stream=stream,
                filters=filters,
                langfuse=langfuse,
            )

        deduplicator = get_deduplicator()

        async def execute_llm_call() -> Dict[str, Any]:
            query_engine_service = self._create_query_engine(notebook, stream=False)
            min_threshold = self._get_min_score_threshold(notebook)
            chat_repo = ChatRepository(session)
            await self._save_user_message(chat_repo, notebook_id, message)

            if stream:
                response_chunks = []
                async for token in query_engine_service.stream_query(
                    query_str=message,
                    filters=filters,
                    user_id=str(user_id),
                    session_id=str(notebook_id),
                ):
                    response_chunks.append(token)

                full_response = "".join(response_chunks)

                async with async_session_factory() as save_session:
                    last_response = query_engine_service.get_last_response()
                    sources = (
                        get_sources_from_response(last_response)
                        if last_response
                        else []
                    )

                    saved_response = await self._save_assistant_response(
                        session=save_session,
                        notebook_id=notebook_id,
                        response_text=full_response,
                        sources=sources,
                        langfuse=langfuse,
                        min_score_threshold=min_threshold,
                    )

                    if "citations" in saved_response:
                        saved_response["_streaming_citations"] = json.dumps(
                            {
                                "type": "metadata",
                                "citations": saved_response["citations"],
                                "confidence": saved_response.get("confidence"),
                            }
                        )

                    saved_response["_streaming_chunks"] = response_chunks
                    return saved_response
            else:
                query_engine_service = self._create_query_engine(notebook, stream=False)
                response = await query_engine_service.aquery(
                    query_str=message,
                    filters=filters,
                    user_id=str(user_id),
                    session_id=str(notebook_id),
                )

                response_text = (
                    response.response
                    if hasattr(response, "response")
                    else str(response)
                )
                sources = get_sources_from_response(response)

                return await self._save_assistant_response(
                    session=session,
                    notebook_id=notebook_id,
                    response_text=response_text,
                    sources=sources,
                    langfuse=langfuse,
                    min_score_threshold=min_threshold,
                )

        try:
            cached_result = await deduplicator.get_or_execute(
                user_id=str(user_id),
                notebook_id=str(notebook_id),
                message=message,
                coro=execute_llm_call(),
            )

            if stream:

                async def stream_from_cache():
                    chunks = cached_result.get("_streaming_chunks", [])
                    for chunk in chunks:
                        yield chunk

                    citations = cached_result.get("_streaming_citations")
                    if citations:
                        yield citations

                return stream_from_cache()
            else:
                return cached_result

        except Exception as e:
            await self._handle_chat_error(
                e, ChatRepository(session), notebook_id, langfuse
            )

    async def _send_research_message(
        self,
        session: AsyncSession,
        notebook: Any,
        notebook_id: UUID,
        user_id: UUID,
        message: str,
        stream: bool,
        filters: Any,
        langfuse: Any,
    ) -> Union[Dict[str, Any], AsyncIterator[str]]:
        """Run multi-step research agent and save the synthesized response."""
        chat_repo = ChatRepository(session)
        await self._save_user_message(chat_repo, notebook_id, message)

        query_engine = self._create_query_engine(notebook, stream=False)
        min_threshold = self._get_min_score_threshold(notebook)
        agent = ResearchAgentService()

        if stream:

            async def stream_research() -> AsyncIterator[str]:
                response_chunks: List[str] = []
                pending_sources: List[Dict[str, Any]] = []

                async for event in agent.run(
                    question=message,
                    query_engine=query_engine,
                    filters=filters,
                    user_id=user_id,
                    notebook_id=notebook_id,
                    min_score_threshold=min_threshold,
                ):
                    if event.startswith("{"):
                        try:
                            parsed = json.loads(event)
                            if parsed.get("type") == "agent_step":
                                yield event
                                continue
                            if parsed.get("type") == "metadata":
                                pending_sources = parsed.get("_sources_for_save", [])
                                continue
                        except json.JSONDecodeError:
                            pass
                    response_chunks.append(event)
                    yield event

                full_response = "".join(response_chunks)
                async with async_session_factory() as save_session:
                    saved = await self._save_assistant_response(
                        session=save_session,
                        notebook_id=notebook_id,
                        response_text=full_response,
                        sources=pending_sources,
                        langfuse=langfuse,
                        min_score_threshold=min_threshold,
                    )

                if "citations" in saved:
                    yield json.dumps(
                        {
                            "type": "metadata",
                            "citations": saved["citations"],
                            "confidence": saved.get("confidence"),
                        }
                    )

            return stream_research()

        # Non-streaming: collect everything then save
        response_chunks: List[str] = []
        pending_sources: List[Dict[str, Any]] = []

        async for event in agent.run(
            question=message,
            query_engine=query_engine,
            filters=filters,
            user_id=user_id,
            notebook_id=notebook_id,
            min_score_threshold=min_threshold,
        ):
            if event.startswith("{"):
                try:
                    parsed = json.loads(event)
                    if parsed.get("type") == "metadata":
                        pending_sources = parsed.get("_sources_for_save", [])
                        continue
                except json.JSONDecodeError:
                    pass
            else:
                response_chunks.append(event)

        full_response = "".join(response_chunks)
        return await self._save_assistant_response(
            session=session,
            notebook_id=notebook_id,
            response_text=full_response,
            sources=pending_sources,
            langfuse=langfuse,
            min_score_threshold=min_threshold,
        )

    async def _save_assistant_response(
        self,
        session: AsyncSession,
        notebook_id: UUID,
        response_text: str,
        sources: List[Dict[str, Any]],
        langfuse: Any = None,
        min_score_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Helper to save assistant response and citations to DB.
        Used by both streaming (post-stream) and regular responses.
        """
        chat_repo = ChatRepository(session)

        # Extract citations using utility
        citations = extract_citations_from_sources(sources)

        # Enrich citations with filenames from database if missing
        citations = await enrich_citations_with_filenames(citations, session)

        # Compute confidence before saving so it can be persisted with the message
        min_threshold = min_score_threshold or self.settings.policy.min_score_threshold
        confidence = compute_confidence_metadata(sources, min_threshold)

        # Save assistant message
        assistant_msg = await chat_repo.add_message(
            notebook_id=notebook_id,
            role=ChatRole.ASSISTANT,
            content=response_text,
            citations=citations if citations else None,
            confidence=confidence,
        )

        logger.info(
            f"Saved assistant message with {len(citations)} citations for notebook {notebook_id}"
        )

        # Update Langfuse trace
        if langfuse:
            langfuse.update_current_trace(
                metadata={
                    "response_length": len(response_text),
                    "citations_count": len(citations),
                    "sources_count": len(sources),
                    "streaming": False,
                }
            )

        formatted_citations = [
            {
                "id": str(assistant_msg.id) + f"_{i}",
                "message_id": str(assistant_msg.id),
                "document_id": str(cit["document_id"]),
                "text_preview": cit["text_preview"],
                "score": cit["score"],
                "page_number": cit.get("page_number"),
                "filename": cit.get("filename"),
            }
            for i, cit in enumerate(citations)
        ]

        return {
            "message": response_text,
            "message_id": str(assistant_msg.id),
            "sources": sources,
            "citations": formatted_citations,
            "confidence": confidence,
        }

    async def get_history(
        self, session: AsyncSession, notebook_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[ChatMessage]:
        """Get chat history for a notebook with pagination."""
        chat_repo = ChatRepository(session)
        history = await chat_repo.get_notebook_history(notebook_id, limit, offset)
        # Return chronological order (oldest first)
        return list(reversed(history))

    async def get_history_count(self, session: AsyncSession, notebook_id: UUID) -> int:
        """Get total count of messages in chat history."""
        chat_repo = ChatRepository(session)
        return await chat_repo.count_notebook_history(notebook_id)

    async def delete_history(self, session: AsyncSession, notebook_id: UUID) -> bool:
        """
        Delete all chat messages for a notebook using batch operation.

        This uses a single DELETE query with WHERE clause for better performance.
        Previous N+1 implementation: 10,000 messages = 10,000 queries (~100s)
        New batch implementation: 10,000 messages = 1 query (~0.1s)
        """

        subquery = select(ChatMessage.id).where(ChatMessage.notebook_id == notebook_id)

        citation_result = await session.execute(
            delete(MessageCitation).where(MessageCitation.message_id.in_(subquery))
        )

        # Then delete messages (single DELETE query)
        result = await session.execute(
            delete(ChatMessage).where(ChatMessage.notebook_id == notebook_id)
        )
        await session.commit()

        deleted_count = result.rowcount
        logger.info(
            f"Deleted {deleted_count} messages for notebook {notebook_id} (batch operation)"
        )
        return deleted_count > 0

    @observe(name="generate_suggestions")
    async def generate_suggestions(
        self, session: AsyncSession, notebook_id: UUID, user_id: UUID
    ) -> Dict[str, Any]:
        """
        Generate contextual suggested questions based on notebook content.
        Uses structured output parsing for reliability.
        """

        # Get documents for this notebook
        doc_repo = DocumentRepository(session)
        documents = await doc_repo.get_by_notebook(notebook_id)

        # Filter to only completed documents
        completed_docs = [
            d for d in documents if d.status == ProcessingStatus.COMPLETED
        ]

        # If no documents, return empty suggestions with guidance
        if not completed_docs:
            return {
                "questions": [],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "document_count": 0,
            }

        # Build context from document names and sample content
        doc_context_parts = []
        for doc in completed_docs[:5]:  # Limit to 5 docs for context
            doc_context_parts.append(f"- {doc.filename}")

        doc_list = "\n".join(doc_context_parts)

        # Fetch some sample content from vector store for richer context
        try:
            vector_store = get_vector_store()
            sample_content = []

            # Query vector store for sample chunks from this notebook
            from qdrant_client.models import (
                Filter,
                FieldCondition,
                MatchValue,
                NamedVector,
            )

            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="metadata.notebook_id",
                        match=MatchValue(value=str(notebook_id)),
                    )
                ]
            )

            # Use random vector search to get diverse samples each time
            dimension = vector_store.embedding_dimension
            random_vector = [random.random() for _ in range(dimension)]

            try:
                results = vector_store.client.search(
                    collection_name=vector_store.collection_name,
                    query_vector=NamedVector(name="text-dense", vector=random_vector),
                    query_filter=filter_condition,
                    limit=5,  # Increased limit for better context coverage
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as e:
                logger.warning(f"Could not fetch vector content samples: {e}")
                results = []

            if results:
                for point in results:
                    if point.payload and "text" in point.payload:
                        text = point.payload["text"][
                            :300
                        ]  # Increased context window slightly
                        sample_content.append(text)

            content_samples = (
                "\n---\n".join(sample_content)
                if sample_content
                else "No content samples available."
            )

        except Exception as e:
            logger.warning(f"Could not fetch vector content samples: {e}")
            content_samples = "Content samples unavailable."

        # OPTIMIZED Prompt - Focus on deep analysis and specific details
        prompt_template = (
            "Generate 3 highly specific, analytical questions about these documents.\n\n"
            f"DOCUMENTS: {doc_list}\n"
            f"SAMPLES: {content_samples}\n\n"
            "RULES:\n"
            "1. Questions MUST be under 15 words.\n"
            "2. Context field must be ONLY the filename (e.g. 'report.pdf').\n"
            "3. Do NOT ask 'What is X?' or generic summary questions.\n"
            "4. Ask about: specific relationships, causal factors, quantitative findings (if any), or tensions between concepts.\n"
            "5. Example Good: 'How does the proposed method improve over standard Transformer attention?'\n"
            "6. Example Bad: 'What is the methodology?'\n"
            "7. Exactly 3 items. Output valid JSON only.\n"
        )

        try:
            # Use generation LLM settings
            provider, model_name, api_key = select_generation_llm_provider(
                self.settings
            )

            llm = create_llamaindex_llm(
                provider=provider,
                api_key=api_key,
                model=model_name,
                temperature=0.4,
                max_tokens=1024,  # Increased to prevent truncation
            )

            program = LLMTextCompletionProgram.from_defaults(
                output_parser=RobustJSONParser(DocumentSuggestionList),
                prompt_template_str=prompt_template,
                llm=llm,
                verbose=False,
            )

            # Execute
            output = await program.acall()

            # Convert to response format
            validated_questions = []
            for i, item in enumerate(output.items[:5]):
                validated_questions.append(
                    {
                        "id": f"q{i + 1}",
                        "text": item.text[:150],
                        "context": item.context[:50] if item.context else "General",
                    }
                )

            logger.info(
                f"Generated {len(validated_questions)} suggestions for notebook {notebook_id} using {provider}/{model_name}"
            )

            return {
                "questions": validated_questions,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "document_count": len(completed_docs),
            }

        except Exception as e:
            logger.error("Failed to generate suggestions: {}", e, exc_info=True)
            # Fallback questions based on document names
            fallback = []
            for i, doc in enumerate(completed_docs[:3]):
                fallback.append(
                    {
                        "id": f"q{i + 1}",
                        "text": f"What are the key points in {doc.filename}?",
                        "context": f"Based on: {doc.filename}",
                    }
                )
            return {
                "questions": fallback,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "document_count": len(completed_docs),
            }

    @observe(name="generate_conversation_suggestions")
    async def generate_conversation_suggestions(
        self, user_message: str, assistant_message: str
    ) -> List[str]:
        """
        Generate dynamic follow-up questions based on the last conversation turn.
        Uses structured output parsing for reliability.
        """
        logger.info(
            f"Generating conversation suggestions for: '{user_message[:50]}...'"
        )

        # Truncate inputs aggressively to save tokens and focus context
        user_context = user_message[:500]
        ai_context = assistant_message[:1000]

        prompt_template = (
            "Generate 3 follow-up questions that help the user explore DEEPER into the topic.\n\n"
            f"USER ASKED: {user_context}\n"
            f"ASSISTANT ANSWERED: {ai_context}\n\n"
            "RULES (MUST FOLLOW):\n"
            "1. NO generic definitions like 'What is X?'. Assume the user is intelligent.\n"
            "2. Questions must explore: downstream implications, potential conflicts, edge cases, or practical application.\n"
            "3. Use phrases like 'How does this impact', 'What are the trade-offs', 'Compare X to Y'.\n"
            "4. Max 25 words per question. Ensure they are detailed enough to be meaningful.\n"
            "5. Output JSON array of 3 strings only.\n\n"
            'EXAMPLE BAD: ["What is RAFT?", "Can you explain more?"]\n'
            'EXAMPLE GOOD: ["How does this approach handle noisy data during training given the constraints?", "What are the specific computational trade-offs compared to traditional methods?"]\n'
        )

        try:
            # Use generation LLM settings (fast model like Gemini Flash)
            provider, model_name, api_key = select_generation_llm_provider(
                self.settings
            )

            llm = create_llamaindex_llm(
                provider=provider,
                api_key=api_key,
                model=model_name,
                temperature=0.3,  # Lower temp for structural stability
                max_tokens=2048,  # Plenty of room for 3 short strings
            )

            program = LLMTextCompletionProgram.from_defaults(
                output_parser=RobustJSONParser(SuggestionList),
                prompt_template_str=prompt_template,
                llm=llm,
                verbose=False,
            )

            # Execute
            output = await program.acall()

            # Extract and validate
            questions = output.questions

            # Final sanity check
            valid_questions = [
                q.strip()[:150]
                for q in questions
                if isinstance(q, str) and "?" in q and len(q) > 5
            ]

            logger.info(
                f"Generated {len(valid_questions)} suggestions using {provider}"
            )
            return valid_questions[:3]

        except Exception as e:
            logger.error(
                f"Failed to generate conversation suggestions: {e}", exc_info=True
            )
            # Fallback is crucial for UX - generate context-aware fallback questions
            return self._generate_fallback_questions(user_message, assistant_message)

    def _generate_fallback_questions(
        self, user_message: str, assistant_message: str
    ) -> List[str]:
        """
        Generate fallback questions when LLM parsing fails.
        Creates analytical questions instead of generic "what is X" questions.
        """
        questions = []

        # Extract potential key terms from the assistant's response
        import re

        words = re.findall(
            r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", assistant_message[:500]
        )
        unique_terms = list(dict.fromkeys(words))[:3]  # Dedupe, take first 3

        # Generate analytical questions, not definition questions
        if unique_terms:
            term = unique_terms[0]
            questions.append(f"What are the main advantages and limitations of {term}?")
            if len(unique_terms) > 1:
                questions.append(
                    f"How does {unique_terms[0]} compare to {unique_terms[1]}?"
                )

        # Add context-aware analytical follow-ups
        if "how" in user_message.lower():
            questions.append("What are the key challenges when implementing this?")
        elif "what" in user_message.lower():
            questions.append("What practical applications does this have?")
        elif "why" in user_message.lower():
            questions.append("What evidence supports this conclusion?")
        else:
            questions.append("Can you provide a concrete example of this in practice?")

        return questions[:3]

    @observe(name="enhance_prompt")
    async def enhance_prompt(self, message: str) -> str:
        """
        Enhance a user prompt using LLM to make it more effective.
        """
        logger.info("Enhancing prompt...")

        prompt_template = (
            "Rewrite the following user prompt to be more detailed, precise, and effective for an AI LLM.\n"
            "Keep the original intent completely but improve clarity, structure, and add necessary context requests.\n"
            "Make it sound professional and sophisticated.\n"
            "Do NOT add preamble or meta-talk like 'Here is the enhanced prompt:'. Just output the enhanced prompt text.\n\n"
            f"ORIGINAL PROMPT: {message}\n\n"
            "ENHANCED PROMPT:"
        )

        try:
            # Use generation LLM settings for speed
            provider, model_name, api_key = select_generation_llm_provider(
                self.settings
            )

            # Using a simple completion call via the underlying library or creating a quick LLM instance
            # We can reuse create_llamaindex_llm
            llm = create_llamaindex_llm(
                provider=provider,
                api_key=api_key,
                model=model_name,
                temperature=0.7,
                max_tokens=1000,
            )

            response = await llm.acomplete(prompt_template)
            return response.text.strip()

        except Exception as e:
            logger.error(f"Error enhancing prompt: {e}")
            return message  # Fallback
