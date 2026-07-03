import asyncio
from typing import Optional
from llama_index.core.indices.query.query_transform import HyDEQueryTransform
from llama_index.core.schema import QueryBundle
from loguru import logger
from src.config import get_settings

class SafeHyDEQueryTransform(HyDEQueryTransform):
    """
    HyDE wrapper that enforces strict timeouts.
    If HyDE takes too long or fails, it falls back to the original query instantly.
    """
    
    async def acall(self, query_bundle_or_str: QueryBundle, metadata=None) -> QueryBundle:
        settings = get_settings()
        timeout = settings.policy.hyde_timeout
        
        try:
            return await asyncio.wait_for(
                super().acall(query_bundle_or_str, metadata),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"HyDE timed out (> {timeout}s). Falling back to original query.")
           
            return query_bundle_or_str if isinstance(query_bundle_or_str, QueryBundle) else QueryBundle(query_bundle_or_str)
        except Exception as e:
            logger.error(f"HyDE failed safely: {e}. Falling back to original query.")
           
            return query_bundle_or_str if isinstance(query_bundle_or_str, QueryBundle) else QueryBundle(query_bundle_or_str)

    def __call__(self, query_bundle_or_str: QueryBundle, metadata=None) -> QueryBundle:
        logger.warning("SafeHyDE called synchronously - skipping protections for now.")
        return super().__call__(query_bundle_or_str, metadata)

