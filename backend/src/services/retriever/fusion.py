from typing import List, Optional
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.retrievers import QueryFusionRetriever, BaseRetriever
from loguru import logger

class FilterEnforcingRetrieverWrapper(BaseRetriever):
    """
    Wrapper to enforce filters on a retriever.
    This ensures that when QueryFusionRetriever generates new queries,
    the original filters (like user_id) are still applied.
    """
    
    def __init__(self, original_retriever: BaseRetriever, filters: Optional[object] = None, **extra_kwargs):
        self._r = original_retriever
        self.filters = filters
        self._extra_kwargs = extra_kwargs
        super().__init__()
    
    def _retrieve(self, query_bundle: QueryBundle, **kwargs) -> List[NodeWithScore]:
        call_kwargs = {**self._extra_kwargs, **kwargs}

        # CRITICAL: Always set filters on query_bundle
        # Handle case where query_bundle doesn't have filters attribute
        existing_filters = getattr(query_bundle, 'filters', None)

        if not existing_filters and self.filters:
            # Ensure attribute exists and set our filters
            if not hasattr(query_bundle, 'filters'):
                object.__setattr__(query_bundle, 'filters', self.filters)
            else:
                query_bundle.filters = self.filters
        elif self.filters:
            # Override with our filters to ensure consistency
            if not hasattr(query_bundle, 'filters'):
                object.__setattr__(query_bundle, 'filters', self.filters)
            else:
                query_bundle.filters = self.filters

        if self.filters:
            filter_keys = [f.key for f in self.filters.filters] if hasattr(self.filters, 'filters') else []
            logger.info(f"FilterEnforcingRetrieverWrapper applying {len(filter_keys)} filters: {filter_keys}")
        else:
            qb_filters = getattr(query_bundle, 'filters', 'NO_ATTRIBUTE')
            logger.error(f"FilterEnforcingRetrieverWrapper: NO FILTERS TO APPLY! QueryBundle filters: {qb_filters}")

        if hasattr(self._r, "_retrieve"):
            try:
                return self._r._retrieve(query_bundle, **call_kwargs)
            except TypeError:
                return self._r._retrieve(query_bundle)

        return self._r.retrieve(query_bundle, **call_kwargs)
        
    async def _aretrieve(self, query_bundle: QueryBundle, **kwargs) -> List[NodeWithScore]:
        call_kwargs = {**self._extra_kwargs, **kwargs}

        # CRITICAL: Always set filters on query_bundle
        # Handle case where query_bundle doesn't have filters attribute
        existing_filters = getattr(query_bundle, 'filters', None)

        if not existing_filters and self.filters:
            # Ensure attribute exists and set our filters
            if not hasattr(query_bundle, 'filters'):
                object.__setattr__(query_bundle, 'filters', self.filters)
            else:
                query_bundle.filters = self.filters
        elif self.filters:
            # Override with our filters to ensure consistency
            if not hasattr(query_bundle, 'filters'):
                object.__setattr__(query_bundle, 'filters', self.filters)
            else:
                query_bundle.filters = self.filters

        if self.filters:
            filter_keys = [f.key for f in self.filters.filters] if hasattr(self.filters, 'filters') else []
            logger.info(f"FilterEnforcingRetrieverWrapper (async) applying {len(filter_keys)} filters: {filter_keys}")
        else:
            qb_filters = getattr(query_bundle, 'filters', 'NO_ATTRIBUTE')
            logger.error(f"FilterEnforcingRetrieverWrapper (async): NO FILTERS TO APPLY! QueryBundle filters: {qb_filters}")

        if hasattr(self._r, "_aretrieve"):
            try:
                return await self._r._aretrieve(query_bundle, **call_kwargs)
            except TypeError:
                return await self._r._aretrieve(query_bundle)

        return await self._r.aretrieve(query_bundle, **call_kwargs)


class ContextAwareQueryFusionRetriever(QueryFusionRetriever):
    """
    Custom QueryFusionRetriever that strictly preserves filters from the original query.
    It wraps the internal retrievers to ensure every generated query inherits the
    original user_id filters and observability context.
    """
    
    def _get_queries(self, original_query: str, num_queries: Optional[int] = None) -> List[QueryBundle]:
        """
        Override to generate QueryBundles with filters preserved.
        This ensures all generated queries inherit the original filters.

        Note: Some versions of QueryFusionRetriever may call this with num_queries parameter.
        """
        # Call parent to generate queries (handle both signatures)
        try:
            query_bundles = super()._get_queries(original_query)
        except TypeError:
            # Fallback if parent expects num_queries
            query_bundles = super()._get_queries(original_query, num_queries or self.num_queries)

        # CRITICAL: Inject filters into all generated QueryBundles
        # AND ensure filters attribute exists on each QueryBundle
        if hasattr(self, '_preserved_filters') and self._preserved_filters:
            for qb in query_bundles:
                # CRITICAL: Ensure filters attribute exists (may not be initialized)
                if not hasattr(qb, 'filters'):
                    # Initialize filters attribute on QueryBundle
                    object.__setattr__(qb, 'filters', self._preserved_filters)
                else:
                    qb.filters = self._preserved_filters

            filter_keys = [f.key for f in self._preserved_filters.filters] if hasattr(self._preserved_filters, 'filters') else []
            logger.info(f"ContextAwareQueryFusionRetriever._get_queries: Injected {len(filter_keys)} filters into {len(query_bundles)} QueryBundles: {filter_keys}")
        else:
            logger.warning(f"ContextAwareQueryFusionRetriever._get_queries: No preserved filters to inject!")
            # Still ensure filters attribute exists (set to None)
            for qb in query_bundles:
                if not hasattr(qb, 'filters'):
                    object.__setattr__(qb, 'filters', None)

        return query_bundles
    
    def _retrieve(self, query_bundle: QueryBundle, **kwargs) -> List[NodeWithScore]:
        original_filters = getattr(query_bundle, 'filters', None)
        original_retrievers = self._retrievers
        
        # CRITICAL: Store filters BEFORE any operations (needed for _get_queries)
        self._preserved_filters = original_filters
        
        # Log filters for debugging
        if original_filters:
            filter_keys = [f.key for f in original_filters.filters] if hasattr(original_filters, 'filters') else []
            logger.info(f"ContextAwareQueryFusionRetriever preserving {len(filter_keys)} filters: {filter_keys}")
        else:
            logger.warning("ContextAwareQueryFusionRetriever: No filters in original query_bundle!")
        
        # Ensure query_bundle has filters
        if original_filters:
            query_bundle.filters = original_filters
        
        # Temporarily wrap retrievers to enforce filters on ANY query bundle passed to them
        # This ensures filters are applied even when QueryFusionRetriever creates new QueryBundles
        wrapped_retrievers = [
            FilterEnforcingRetrieverWrapper(r, filters=original_filters, **kwargs) 
            for r in original_retrievers
        ]
        self._retrievers = wrapped_retrievers
        
        try:
            result = super()._retrieve(query_bundle)
            return result
        finally:
            # Restore original retrievers
            self._retrievers = original_retrievers
            self._preserved_filters = None

    async def _aretrieve(self, query_bundle: QueryBundle, **kwargs) -> List[NodeWithScore]:
        original_filters = getattr(query_bundle, 'filters', None)
        original_retrievers = self._retrievers

        # CRITICAL: Try to recover filters from instance variable first (set by FilterPreservingQueryEngine)
        if not original_filters and hasattr(self, '_preserved_filters') and self._preserved_filters:
            original_filters = self._preserved_filters
            # Ensure filters attribute exists before setting
            if not hasattr(query_bundle, 'filters'):
                object.__setattr__(query_bundle, 'filters', original_filters)
            else:
                query_bundle.filters = original_filters
            logger.warning(f"ContextAwareQueryFusionRetriever: Recovered filters from instance variable")

        # CRITICAL: Store filters BEFORE any operations (needed for _get_queries)
        # QueryFusionRetriever may create new QueryBundles internally, so we need to preserve filters
        self._preserved_filters = original_filters

        # Log filters for debugging
        if original_filters:
            filter_keys = [f.key for f in original_filters.filters] if hasattr(original_filters, 'filters') else []
            logger.info(f"ContextAwareQueryFusionRetriever (async) preserving {len(filter_keys)} filters: {filter_keys}")
        else:
            logger.error("ContextAwareQueryFusionRetriever (async): No filters in query_bundle! This will cause data leakage!")

        # Ensure query_bundle has filters attribute (even if None)
        if not hasattr(query_bundle, 'filters'):
            object.__setattr__(query_bundle, 'filters', original_filters)
        elif original_filters:
            query_bundle.filters = original_filters
        
        # Temporarily wrap retrievers to enforce filters on ANY query bundle passed to them
        # This ensures filters are applied even when QueryFusionRetriever creates new QueryBundles
        wrapped_retrievers = [
            FilterEnforcingRetrieverWrapper(r, filters=original_filters, **kwargs) 
            for r in original_retrievers
        ]
        self._retrievers = wrapped_retrievers
        
        try:
            result = await super()._aretrieve(query_bundle)
            return result
        finally:
            # Restore original retrievers
            self._retrievers = original_retrievers
            self._preserved_filters = None
