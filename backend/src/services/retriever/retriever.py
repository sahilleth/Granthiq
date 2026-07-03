"""
Retriever module facade.

This module re-exports components from the split retriever modules:
- HybridRetriever -> hybrid.py
- ContextAwareQueryFusionRetriever -> fusion.py
- get_retriever, get_auto_merging_retriever -> factory.py
"""

from src.services.retriever.hybrid import HybridRetriever
from src.services.retriever.fusion import ContextAwareQueryFusionRetriever
from src.services.retriever.factory import get_retriever, get_auto_merging_retriever

__all__ = [
    "HybridRetriever",
    "ContextAwareQueryFusionRetriever",
    "get_retriever",
    "get_auto_merging_retriever",
]
