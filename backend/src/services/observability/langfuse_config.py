from typing import Dict, Any
import os
from loguru import logger
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
from src.config import get_settings
from langfuse import get_client
_langfuse_initialized = False
_langfuse_client = None


def setup_langfuse() -> bool:
    """
    Initialize Langfuse tracing for LlamaIndex.
    
    Returns:
        True if Langfuse was successfully initialized, False otherwise
    """
    global _langfuse_initialized, _langfuse_client
    
    if _langfuse_initialized:
        return True
    
    settings = get_settings()
    
    if not settings.langfuse.enabled:
        logger.debug("Langfuse tracing is disabled")
        return False
    
   
    if not settings.langfuse.public_key or not settings.langfuse.secret_key:
        logger.warning(
            "Langfuse API keys not found. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable tracing."
        )
        return False
    
    try:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse.public_key
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse.secret_key
        os.environ["LANGFUSE_HOST"] = settings.langfuse.host
        try:
            _langfuse_client = get_client()
            
            if _langfuse_client.auth_check():
                logger.info(f"Langfuse client authenticated and ready: {settings.langfuse.host}")
            else:
                logger.warning("Langfuse authentication failed. Please check your credentials.")
                return False
        except ImportError as e:
            logger.error(f"Could not import Langfuse: {e}. Install with: pip install langfuse")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Langfuse client: {e}")
            return False
     
        try:
            LlamaIndexInstrumentor().instrument()
            logger.info("LlamaIndex instrumentation initialized for Langfuse")
        except ImportError as e:
            logger.warning(
                f"Could not import OpenInference LlamaIndex instrumentation: {e}. "
                f"Install with: pip install openinference-instrumentation-llama-index"
            )
         
        except Exception as e:
            logger.warning(
                f"Failed to initialize OpenInference LlamaIndex instrumentation: {e}. "
                f"This may be due to a version compatibility issue between openinference-instrumentation-llama-index "
                f"and llama-index. Manual tracing will still work."
            )
        _langfuse_initialized = True
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        return False


def get_langfuse_client():
    """
    Get the Langfuse client instance.
    
    Returns:
        Langfuse client or None if not initialized
    """
    if not _langfuse_initialized:
        setup_langfuse()
    return _langfuse_client


def flush_langfuse():
    """Flush pending events to Langfuse (useful for short-lived applications)."""
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse events: {e}")


def get_langfuse_status() -> Dict[str, Any]:
    """
    Get Langfuse connection status and configuration.
    
    Returns:
        Dictionary with status information
    """
    settings = get_settings()
    
    status = {
        "enabled": settings.langfuse.enabled,
        "initialized": _langfuse_initialized,
        "has_client": _langfuse_client is not None,
        "has_keys": bool(settings.langfuse.public_key and settings.langfuse.secret_key),
        "host": settings.langfuse.host,
        "authenticated": False,
    }
    
    if _langfuse_client:
        try:
            status["authenticated"] = _langfuse_client.auth_check()
        except Exception as e:
            logger.debug(f"Could not check Langfuse auth status: {e}")
            status["error"] = str(e)
    
    return status

def _auto_setup():
    """Auto-initialize Langfuse if enabled in config."""
    try:
        setup_langfuse()
    except Exception as e:
        logger.debug(f"Auto-setup of Langfuse failed: {e}")

_auto_setup()

