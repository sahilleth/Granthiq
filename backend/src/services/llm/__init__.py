"""LLM module - Unified LiteLLM factory."""

# Apply Pydantic compatibility fixes before importing LlamaIndex modules
try:
    from utils.pydantic_compat import _patch_llamaindex_pydantic_compat
    _patch_llamaindex_pydantic_compat()
except ImportError:
    pass

from typing import Union, Optional
from llama_index.core.llms.llm import LLM as BaseLLM
from src.services.llm.base import LLMConfig, LLMResponse, LLMProvider
from src.services.llm.factory import create_llamaindex_llm
from src.services.llm.prompts import (
    RAG_SYSTEM_PROMPT,
    CONVERSATIONAL_SYSTEM_PROMPT,
    TECHNICAL_SYSTEM_PROMPT,
    RAG_PROMPT_TEMPLATE,
    RAG_WITH_HISTORY_TEMPLATE,
    SUMMARIZATION_TEMPLATE,
    build_context,
    build_rag_prompt,
    format_chat_history,
)


def create_llm(
    provider: str,
    api_key: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = None,
    **kwargs
) -> BaseLLM:
    """
    Create LLM instance using LiteLLM (backward compatibility wrapper).
    
    This replaces the old individual provider wrappers (GroqLLM, GeminiLLM, OpenAILLM)
    with the unified LiteLLM factory.
    
    Args:
        provider: 'groq', 'gemini', or 'openai'
        api_key: API key
        model: Model name (optional, uses defaults)
        temperature: Temperature for generation (0.0 to 2.0)
        max_tokens: Maximum tokens to generate
        **kwargs: Additional configuration options
    
    Returns:
        LlamaIndex BaseLLM instance (LiteLLM)
    """
    
    # Defaults mapping for backward compatibility
    if not model:
        if provider == "groq":
            model = "llama-3.3-70b-versatile"
        elif provider == "gemini":
            model = "gemini-2.5-flash"
        elif provider == "openai":
            model = "gpt-4-turbo"
            
    return create_llamaindex_llm(
        provider=provider,
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens or 2048, # Default if None
    )


def get_available_models(provider: str) -> dict:
    """
    Get available models for a provider.
    Note: This is a static list for now, preserving old behavior.
    """
    provider = provider.lower()
    
    if provider == "groq":
        return {
            "llama-3.3-70b-versatile": "Best overall - 70B model",
            "llama-3.1-8b-instant": "Fastest - 8B model",
            "openai/gpt-oss-120b": "OpenAI GPT OSS 120B",
        }
    elif provider == "gemini":
        return {
             "gemini-2.5-flash": "Fast & multimodal",
             "gemini-1.5-pro": "Reasoning & large context",
        }
    elif provider == "openai":
        return {
            "gpt-4-turbo": "GPT-4 Turbo",
            "gpt-4o": "GPT-4o",
            "gpt-3.5-turbo": "Fast & cheap",
        }
    else:
        raise ValueError(f"Unknown provider: {provider}")


__all__ = [
    # Core classes
    "LLMConfig",
    "LLMResponse",
    "LLMProvider",
    
    # Factory functions
    "create_llm",
    "create_llamaindex_llm",
    "get_available_models",
    
    # System prompts
    "RAG_SYSTEM_PROMPT",
    "CONVERSATIONAL_SYSTEM_PROMPT",
    "TECHNICAL_SYSTEM_PROMPT",
    
    # Templates
    "RAG_PROMPT_TEMPLATE",
    "RAG_WITH_HISTORY_TEMPLATE",
    "SUMMARIZATION_TEMPLATE",
    
    # Helper functions
    "build_context",
    "build_rag_prompt",
    "format_chat_history",
]
