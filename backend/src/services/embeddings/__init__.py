"""Embedding configuration module."""

from src.services.embeddings.embedding_config import (
    configure_llamaindex_embed_model,
    get_llamaindex_embed_model,
)

__all__ = [
    "configure_llamaindex_embed_model",
    "get_llamaindex_embed_model",
]
