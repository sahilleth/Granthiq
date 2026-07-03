from typing import Optional
import os
from llama_index.core import Settings
from loguru import logger
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from src.config import get_settings


def configure_llamaindex_embed_model(
    model_name: Optional[str] = None,
) -> None:
    """
    Configure LlamaIndex's global embed_model setting using native HuggingFaceEmbedding.
    
    This ensures that queries are converted to embeddings using the same
    model that was used for indexing, ensuring consistency.
    
    Args:
        model_name: Model name to load. If None, uses config default.
    """
    
    settings = get_settings()
    
    if model_name is None:
        model_name = settings.embedding.model
    
    logger.info(f"Configuring LlamaIndex embed_model with HuggingFace: {model_name}")
    logger.debug(f"Embedding model from config: {settings.embedding.model}")
    

    embed_model = None
    

    os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")
    logger.debug(f"TRANSFORMERS_OFFLINE env var: {os.environ.get('TRANSFORMERS_OFFLINE')}")
    

    try:
        logger.info(f"Attempting to load HuggingFaceEmbedding: {model_name}")
        logger.debug("Creating HuggingFaceEmbedding instance with device='cpu'...")
        embed_model = HuggingFaceEmbedding(
            model_name=model_name,
            device='cpu', 
        )
        logger.info(f"Successfully loaded HuggingFaceEmbedding: {model_name}")
    except Exception as e1:
        error_msg = str(e1).lower()
        logger.warning(f"First attempt to load HuggingFaceEmbedding failed: {type(e1).__name__}: {e1}")
        logger.debug(f"Full error traceback for first attempt:", exc_info=True)
        
        try:
            logger.info("Retrying with trust_remote_code=True...")
            embed_model = HuggingFaceEmbedding(
                model_name=model_name,
                trust_remote_code=True,
                device='cpu',
            )
            logger.info(f"Successfully loaded HuggingFaceEmbedding with trust_remote_code=True")
        except Exception as e2:
            logger.warning(f"Second attempt failed: {type(e2).__name__}: {e2}")
            logger.debug(f"Full error traceback for second attempt:", exc_info=True)
            

            try:
                logger.info("Retrying with minimal settings (no device/trust_remote_code)...")
                embed_model = HuggingFaceEmbedding(model_name=model_name)
                logger.info(f"Successfully loaded HuggingFaceEmbedding with minimal settings")
            except Exception as e3:
                logger.error(
                    f"Failed to load HuggingFaceEmbedding after all 3 attempts.\n"
                    f"Attempt 1: {type(e1).__name__}: {str(e1)[:200]}\n"
                    f"Attempt 2: {type(e2).__name__}: {str(e2)[:200]}\n"
                    f"Attempt 3: {type(e3).__name__}: {str(e3)[:200]}",
                    exc_info=True
                )
                raise RuntimeError(
                    f"Cannot load embedding model {model_name}. "
                    f"All attempts failed. Last error: {type(e3).__name__}: {e3}\n"
                    "Try running: pip install --upgrade torch transformers sentence-transformers"
                ) from e3
    except Exception as e:
        logger.error(f"Unexpected error loading HuggingFaceEmbedding: {type(e).__name__}: {e}", exc_info=True)
        raise
    

    # Set the embed_model in LlamaIndex Settings
    logger.debug(f"Setting Settings.embed_model to {type(embed_model).__name__}")
    Settings.embed_model = embed_model
    
    logger.info(
        f"Configured LlamaIndex embed_model: {model_name} (type: {type(embed_model).__name__})"
    )


def get_llamaindex_embed_model():
    """
    Get the currently configured LlamaIndex embed_model.
    
    Returns:
        The embed_model from Settings, or None if not configured.
    """
    return Settings.embed_model
