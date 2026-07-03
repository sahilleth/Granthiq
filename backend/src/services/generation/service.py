import os
from typing import Optional, Literal, Union, List
from uuid import UUID

from loguru import logger
from llama_index.core.response_synthesizers import ResponseMode

from src.config import get_settings
# Note: setup_langfuse() is called once at app startup (see app.py)
from langfuse import observe, Langfuse
from src.services.query.builder import QueryEngineBuilder
from src.services.query.response_utils import build_query_bundle
from src.services.generation.generators.podcast import PodcastGenerator
from src.services.generation.generators.quiz import QuizGenerator
from src.services.generation.generators.flashcard import FlashcardGenerator
from src.services.generation.generators.mindmap import MindMapGenerator
from src.services.generation.audio_generator import AudioGenerator
from src.schemas.content import PodcastScript, Quiz, FlashcardDeck, MindMap
from src.services.llm.factory import create_llamaindex_llm
from src.services.llm.provider_selector import select_generation_llm_provider 
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.repositories.document import DocumentRepository
from src.db.repositories.content import ContentRepository
from src.db.models import ContentType, ProcessingStatus
from src.db.repositories.notebook import NotebookRepository

_generation_service_instance: Optional["GenerationService"] = None


def get_generation_service() -> "GenerationService":
    """
    Get or create the singleton GenerationService instance.
    
    First call initializes the service (slow, ~20-30s).
    Subsequent calls return the cached instance (fast, <1ms).
    """
    global _generation_service_instance
    
    if _generation_service_instance is None:
        logger.info("Creating singleton GenerationService...")
        _generation_service_instance = GenerationService()
        logger.info("GenerationService singleton created and cached")
    
    return _generation_service_instance


class GenerationService:
    def __init__(self):
        self.settings = get_settings()
        # Note: setup_langfuse() is called once at app startup (see app.py)

        logger.info("Initializing Generation Engine...")
        
       
        builder = QueryEngineBuilder(self.settings)
        self.engine = (
            builder
            .with_llm() 
            .with_retriever(
                similarity_top_k=20, 
                fusion_num_queries=1 
            )
            .with_synthesizer(
                response_mode=ResponseMode.TREE_SUMMARIZE,
                streaming=False
            )
            .build() 
        )
        
        # Select LLM provider using centralized utility
        provider, model_name, api_key = select_generation_llm_provider(self.settings)

        self.gen_llm = create_llamaindex_llm(
            provider=provider,
            api_key=api_key,
            model=model_name,
            temperature=0.2,
            max_tokens=8192  
        )
        self.model_name = model_name
        
        logger.info(f"GenerationService ready. Using {provider} ({model_name}) model with 8192 max tokens.")

    @observe(name="generate_content")
    async def generate_content(
        self, 
        session: AsyncSession,
        content_type: Literal["podcast", "quiz", "flashcard", "mindmap"],
        notebook_id: UUID,
        document_ids: Optional[List[UUID]] = None,
        user_id: Optional[UUID] = None,
        content_id: Optional[UUID] = None  # If provided, use existing record instead of creating new
    ) -> Union[PodcastScript, Quiz, FlashcardDeck, MindMap, None]:
        """
        Generate content for a notebook, optionally filtered by specific documents.
        If document_ids is None, generates content from all documents in the notebook.
        """
        langfuse = Langfuse()
        if langfuse:
            langfuse.update_current_trace(
                metadata={"model": self.model_name}
            )

        content_repo = ContentRepository(session)
        doc_repo = DocumentRepository(session)
        
        # First, verify notebook exists and user has access
        
        notebook_repo = NotebookRepository(session)
        notebook = await notebook_repo.get_notebook(notebook_id, user_id)
        if not notebook:
            logger.error("Notebook {} not found or access denied for user {}", notebook_id, user_id)
            return None  # This will cause router to return 400, but router should handle 404
        
        # Convert content_type string to ContentType enum
        content_type_enum = ContentType(content_type)
        
        # Determine which documents to use
        if not document_ids:
            logger.info(f"No document_ids provided. Fetching all documents for notebook {notebook_id}")
            docs = await doc_repo.get_by_notebook(notebook_id)
            document_ids = [doc.id for doc in docs]

            if not document_ids:
                logger.error("No documents found for notebook {}. Aborting generation.", notebook_id)
                return None
        
        logger.info(f"Step 1: Retrieving comprehensive context for {len(document_ids)} document(s)")

        try:
            # Build query with document_id filter (supports list via IN operator)
            query_str = "Provide a comprehensive, detailed, factual summary of the entire document content, covering all main topics and key details."
            
            # Use list of document_ids for filtering (build_query_bundle handles IN operator)
            filters = {
                "document_id": document_ids if len(document_ids) > 1 else document_ids[0],
                "notebook_id": str(notebook_id)
            }
            
            query_bundle = build_query_bundle(
                query_str=query_str,
                filters=filters,
                user_id=str(user_id) if user_id else None,
                anonymous_user_id=self.settings.anonymous_user_id
            )

            retrieval_response = await self.engine.aquery(query_bundle)
            context_text = retrieval_response.response
            
            if "I'm sorry" in context_text or not context_text:
                logger.warning("Generation Refused: Insufficient context")
                return None

            logger.info(f"Step 2: Generating {content_type} (Context length: {len(context_text)} chars)...")
            
            # Use existing content_id if provided (from task queue), otherwise create new record
            # If multiple documents, we'll use the first one as primary document_id
            # or None if generating from all documents
            primary_document_id = document_ids[0] if len(document_ids) == 1 else None
            
            if content_id:
                # Reuse existing placeholder record created by router/task queue
                content_record_id = content_id
                # Update status to PROCESSING
                await content_repo.update_status(content_id, ProcessingStatus.PROCESSING)
                logger.info(f"Using existing content record: {content_id}")
            else:
                # Create new content record (sync mode or direct call)
                content_record = await content_repo.create_content(
                    notebook_id=notebook_id,
                    content_type=content_type,
                    document_id=primary_document_id,
                    status=ProcessingStatus.PROCESSING
                )
                content_record_id = content_record.id
            
            # Generate content
            result = None
            if content_type == "podcast":
                generator = PodcastGenerator(self.gen_llm)
                result = await generator.generate(context=context_text)

                # Generate Audio
                try:
                    audio_gen = AudioGenerator()
                    audio_result = await audio_gen.generate_podcast_audio(
                        result, 
                        notebook_id=str(notebook_id),
                        user_id=str(user_id) if user_id else None,
                        filename_prefix=f"podcast_{content_record_id}" # Use ID directly
                    )
                    if audio_result:
                        storage_key, audio_url, duration = audio_result
                        # Store storage_key in audio_url field to allow regenerating signed URLs
                        result.audio_url = storage_key 
                        result.audio_duration = duration
                        logger.info(f"Audio generated for podcast: {storage_key} ({duration:.2f}s)")
                except Exception as e:
                    logger.error("Audio generation failed: {}", e)
                    # Continue without audio, script is still valid
                
            elif content_type == "quiz":
                generator = QuizGenerator(self.gen_llm)
                result = await generator.generate(context=context_text)
            
            elif content_type == "flashcard":
                generator = FlashcardGenerator(self.gen_llm)
                result = await generator.generate(context=context_text)
            
            elif content_type == "mindmap":
                generator = MindMapGenerator(self.gen_llm)
                result = await generator.generate(context=context_text)
            
            
              
            
            # Save generated content to database
            # Save generated content to database
            if result:
                content_dict = result.model_dump() if hasattr(result, 'model_dump') else result.dict()
                audio_url_update = getattr(result, 'audio_url', None)

                await content_repo.update_content(
                    content_id=content_record_id,
                    content_data=content_dict,
                    content_type=content_type_enum,
                    document_id=primary_document_id,
                    status=ProcessingStatus.COMPLETED,
                    audio_url=audio_url_update
                )
                logger.info(f"Successfully generated and saved {content_type} (ID: {content_record_id})")
            else:
                await content_repo.update_content(
                    content_id=content_record_id,
                    content_data={},
                    content_type=content_type_enum,
                    status=ProcessingStatus.FAILED
                )
            
            return result
            
        except Exception as e:
            logger.error("Error generating content: {}", e, exc_info=True)
            # Update content record to FAILED status if it exists
            try:
                if 'content_record_id' in locals():
                    await content_repo.update_content(
                        content_id=content_record_id,
                        content_data={},
                        content_type=content_type_enum,
                        status=ProcessingStatus.FAILED
                    )
            except Exception as update_error:
                logger.warning(f"Failed to update content status to FAILED: {update_error}")
            return None
