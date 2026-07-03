from typing import  Any
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.core.base.response.schema import  RESPONSE_TYPE
from loguru import logger


class FilterPreservingQueryEngine(BaseQueryEngine):
    """
    Wrapper around any query engine that ensures QueryBundle filters are preserved.

    This is critical for multi-tenant applications where filters prevent data leakage.
    """

    def __init__(self, query_engine: BaseQueryEngine):
        """Initialize with the underlying query engine."""
        self._engine = query_engine
        super().__init__(callback_manager=getattr(query_engine, 'callback_manager', None))

    def _query(self, query_bundle: QueryBundle) -> RESPONSE_TYPE:
        """Synchronous query with filter preservation."""
        # Log filter status
        if hasattr(query_bundle, 'filters') and query_bundle.filters:
            filter_keys = [f.key for f in query_bundle.filters.filters] if hasattr(query_bundle.filters, 'filters') else []
            logger.info(f"FilterPreservingQueryEngine._query: Preserving {len(filter_keys)} filters: {filter_keys}")
        else:
            logger.warning(f"FilterPreservingQueryEngine._query: No filters to preserve!")

        # Call underlying engine
        return self._engine.query(query_bundle)

    async def _aquery(self, query_bundle: QueryBundle) -> RESPONSE_TYPE:
        """Asynchronous query with filter preservation."""
        # Log filter status
        original_filters = getattr(query_bundle, 'filters', None)

        if original_filters:
            filter_keys = [f.key for f in original_filters.filters] if hasattr(original_filters, 'filters') else []
            logger.info(f"FilterPreservingQueryEngine._aquery: Preserving {len(filter_keys)} filters: {filter_keys}")

            # CRITICAL: Store filters on ALL levels of the engine hierarchy
            # TransformQueryEngine (HyDE) will create new QueryBundles without filters,
            # so we need to ensure retrievers can recover filters from instance variables

            # 1. Store on TransformQueryEngine's base_query_engine
            if hasattr(self._engine, '_query_engine'):
                base_engine = self._engine._query_engine
                if hasattr(base_engine, 'retriever'):
                    base_engine.retriever._preserved_filters = original_filters
                    logger.debug(f"Stored filters on base_engine.retriever")

            # 2. Store on direct retriever if available
            if hasattr(self._engine, 'retriever'):
                self._engine.retriever._preserved_filters = original_filters
                logger.debug(f"Stored filters on engine.retriever")

            # 3. Traverse and find retriever in the engine hierarchy
            engine = self._engine
            max_depth = 5
            for i in range(max_depth):
                if hasattr(engine, 'retriever'):
                    engine.retriever._preserved_filters = original_filters
                    logger.debug(f"Stored filters on retriever at depth {i}")
                    break
                elif hasattr(engine, '_query_engine'):
                    engine = engine._query_engine
                elif hasattr(engine, '_engine'):
                    engine = engine._engine
                else:
                    break
        else:
            logger.warning(f"FilterPreservingQueryEngine._aquery: No filters to preserve!")

        # Call underlying engine (filters stored on retrievers will be recovered by ContextAwareQueryFusionRetriever)
        return await self._engine.aquery(query_bundle)

    def _get_prompt_modules(self) -> dict:
        """Get prompt modules from underlying engine."""
        if hasattr(self._engine, '_get_prompt_modules'):
            return self._engine._get_prompt_modules()
        return {}


class FilterInjectingTransformQueryEngine(BaseQueryEngine):
    """
    Wrapper that injects filters into QueryBundles after query transformations.

    Use this to wrap TransformQueryEngine (HyDE) to ensure filters survive transformation.
    """

    def __init__(self, transform_engine: BaseQueryEngine, original_filters: Any = None):
        """
        Initialize with transform engine and filters to inject.

        Args:
            transform_engine: The TransformQueryEngine (e.g., with HyDE)
            original_filters: MetadataFilters to inject after transformation
        """
        self._engine = transform_engine
        self._original_filters = original_filters
        super().__init__(callback_manager=getattr(transform_engine, 'callback_manager', None))

    def _query(self, query_bundle: QueryBundle) -> RESPONSE_TYPE:
        """Synchronous query with filter injection."""
        # Store original filters
        original_filters = getattr(query_bundle, 'filters', None) or self._original_filters

        if original_filters:
            filter_keys = [f.key for f in original_filters.filters] if hasattr(original_filters, 'filters') else []
            logger.info(f"FilterInjectingTransformQueryEngine._query: Will inject {len(filter_keys)} filters after transformation: {filter_keys}")

        # Ensure filters are set before transformation
        if original_filters:
            query_bundle.filters = original_filters

        # Call transform engine (this may create new QueryBundles internally)
        # We need to ensure the retriever gets filters
        response = self._engine.query(query_bundle)

        return response

    async def _aquery(self, query_bundle: QueryBundle) -> RESPONSE_TYPE:
        """Asynchronous query with filter injection."""
        # Store original filters
        original_filters = getattr(query_bundle, 'filters', None) or self._original_filters

        if original_filters:
            filter_keys = [f.key for f in original_filters.filters] if hasattr(original_filters, 'filters') else []
            logger.info(f"FilterInjectingTransformQueryEngine._aquery: Will inject {len(filter_keys)} filters after transformation: {filter_keys}")
        else:
            logger.error(f"FilterInjectingTransformQueryEngine._aquery: NO FILTERS TO INJECT! This will cause data leakage!")

        # Ensure filters are set before transformation
        if original_filters:
            query_bundle.filters = original_filters

        # Call transform engine (this may create new QueryBundles internally)
        response = await self._engine.aquery(query_bundle)

        return response

    def _get_prompt_modules(self) -> dict:
        """Get prompt modules from underlying engine."""
        if hasattr(self._engine, '_get_prompt_modules'):
            return self._engine._get_prompt_modules()
        return {}
