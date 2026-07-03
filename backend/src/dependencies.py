from typing import Annotated, Optional
from functools import lru_cache

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import get_settings, Settings
from src.db.session import async_session_factory
from src.services.chat.service import ChatService
from src.services.query.query_engine import QueryEngineService
from src.services.storage import StorageService, get_storage_service
from src.services.embeddings.embedding_config import get_llamaindex_embed_model


# Database Session Dependency
async def get_db_session() -> AsyncSession:
    """
    Dependency that provides an async database session.

    Usage:
        async def my_route(session: Annotated[AsyncSession, Depends(get_db_session)]):
            # Use session
            pass
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


# Settings Dependency (already cached via lru_cache)
def get_app_settings() -> Settings:
    """
    Dependency that provides application settings.

    Cached via lru_cache for performance.
    """
    return get_settings()


# Query Engine Service Dependency
@lru_cache(maxsize=1)
def _create_query_engine_service(
    llm_provider: Optional[str] = None,
    streaming: Optional[bool] = None,
    similarity_top_k: Optional[int] = None,
) -> QueryEngineService:
    """
    Internal factory for QueryEngineService with caching.

    Uses lru_cache to ensure singleton behavior while remaining testable.
    """
    return QueryEngineService(
        llm_provider=llm_provider,
        streaming=streaming,
        similarity_top_k=similarity_top_k
    )


def get_query_engine_service(
    settings: Annotated[Settings, Depends(get_app_settings)],
    llm_provider: Optional[str] = None,
    streaming: Optional[bool] = None,
) -> QueryEngineService:
    """
    Dependency that provides QueryEngineService.

    Can be overridden in tests using app.dependency_overrides.

    Usage:
        async def my_route(
            query_engine: Annotated[QueryEngineService, Depends(get_query_engine_service)]
        ):
            result = await query_engine.aquery("What is RAG?")
    """
    # Use settings defaults if not provided
    provider = llm_provider or settings.llm.provider
    stream = streaming if streaming is not None else settings.rag.enable_streaming

    return _create_query_engine_service(
        llm_provider=provider,
        streaming=stream,
        similarity_top_k=settings.rag.top_k_results
    )


# Chat Service Dependency (Singleton)
@lru_cache(maxsize=1)
def _create_chat_service() -> ChatService:
    """
    Internal singleton factory for ChatService.

    Using lru_cache ensures only one instance is created,
    avoiding repeated setup_langfuse() calls.
    """
    return ChatService()


def get_chat_service(
    settings: Annotated[Settings, Depends(get_app_settings)] = None
) -> ChatService:
    """
    Dependency that provides ChatService (singleton).

    Cached to avoid repeated Langfuse initialization.

    Usage:
        async def send_message(
            chat_service: Annotated[ChatService, Depends(get_chat_service)]
        ):
            result = await chat_service.send_message(...)
    """
    return _create_chat_service()


# Storage Service Dependency (uses existing singleton)
def get_storage_dependency(
    settings: Annotated[Settings, Depends(get_app_settings)]
) -> StorageService:
    """
    Dependency that provides StorageService.

    Uses existing get_storage_service() singleton.

    Usage:
        async def upload_file(
            storage: Annotated[StorageService, Depends(get_storage_dependency)]
        ):
            url = await storage.upload(...)
    """
    return get_storage_service()


# Embedding Model Dependency
@lru_cache(maxsize=1)
def _get_embedding_model(model_name: str):
    """Cached embedding model creation."""
    return get_llamaindex_embed_model(model_name)


def get_embedding_service(
    settings: Annotated[Settings, Depends(get_app_settings)]
):
    """
    Dependency that provides embedding model.

    Usage:
        async def embed_text(
            embed_model: Annotated[Any, Depends(get_embedding_service)]
        ):
            embeddings = embed_model.get_text_embedding("text")
    """
    return _get_embedding_model(settings.embedding.model)


# Utility: Clear all caches (for testing)
def clear_dependency_caches():
    """
    Clear all LRU caches used by dependencies.

    Useful for testing to ensure fresh instances.

    Usage in tests:
        @pytest.fixture(autouse=True)
        def clear_caches():
            clear_dependency_caches()
            yield
    """
    _create_query_engine_service.cache_clear()
    _create_chat_service.cache_clear()
    _get_embedding_model.cache_clear()


# Type aliases for convenience
DBSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
QueryEngine = Annotated[QueryEngineService, Depends(get_query_engine_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
StorageDep = Annotated[StorageService, Depends(get_storage_dependency)]
