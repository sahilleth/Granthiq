"""
LLM provider selection utilities.
Centralizes provider selection logic for chat and generation services.
"""
from typing import Optional, Tuple
from loguru import logger

from src.config import Settings, get_settings


def select_chat_llm_provider(settings: Optional[Settings] = None) -> Optional[str]:
    """
    Select LLM provider for chat service.
    
    Priority: Groq (fast inference, high rate limits) > configured provider
    
    Args:
        settings: Optional Settings instance (uses get_settings() if None)
        
    Returns:
        Provider name ("groq" or None to use configured default)
    """
    if settings is None:
        settings = get_settings()
    
    # Respect the configured provider if it's explicitly set to something specific
    # The default in config.py is "gemini" (as of recent changes)
    if settings.llm.provider == "gemini":
        logger.info(f"Using configured provider (Gemini) for chat: {settings.llm.model_name}")
        return None
        
    if settings.llm.groq_api_key:
        logger.info("Using Groq for chat - fast inference and high rate limits")
        return "groq"
    else:
        logger.warning("Groq API key not found. Using configured provider for chat.")
        logger.info(f"Chat will use provider: {settings.llm.provider}")
        return None


def select_generation_llm_provider(settings: Optional[Settings] = None) -> Tuple[str, str, Optional[str]]:
    """
    Select LLM provider for content generation service.

    Priority: Groq (reliable JSON output, fast inference) > Gemini > configured provider
    Groq is preferred for generation tasks due to more reliable structured output.

    Args:
        settings: Optional Settings instance (uses get_settings() if None)

    Returns:
        Tuple of (provider, model_name, api_key)
    """
    if settings is None:
        settings = get_settings()

    # Priority 1: Groq (best for reliable JSON output)
    if settings.llm.groq_api_key:
        provider = "groq"
        api_key = settings.llm.groq_api_key
        model_name = "llama-3.3-70b-versatile"  # Good balance of speed and quality
        logger.info(f"Using Groq for generation: {model_name}")
        return provider, model_name, api_key

    # Priority 2: Gemini (fallback)
    if settings.llm.gemini_api_key:
        provider = "gemini"
        api_key = settings.llm.gemini_api_key
        model_name = "gemini-2.5-flash"
        logger.info(f"Using Gemini for generation: {model_name}")
        return provider, model_name, api_key

    # Priority 3: Configured provider (last resort)
    logger.warning("No Groq or Gemini API keys found. Using configured provider.")
    provider = settings.llm.provider
    api_key = getattr(settings.llm, f'{provider}_api_key', None)
    model_name = settings.llm.model_name

    return provider, model_name, api_key
