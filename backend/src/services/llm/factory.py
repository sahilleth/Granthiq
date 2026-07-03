from typing import Optional
from llama_index.core.llms.llm import LLM as BaseLLM
from llama_index.llms.litellm import LiteLLM

def create_llamaindex_llm(
    provider: str,
    api_key: Optional[str],
    model: str,
    temperature: float,
    max_tokens: int,
) -> BaseLLM:
    """
    Create LlamaIndex LLM instance using LiteLLM.
    
    Unified factory that handles all providers (Groq, Gemini, OpenAI, etc.)
    via LiteLLM.
    
    Args:
        provider: 'groq', 'gemini', or 'openai'
        api_key: API key for the provider
        model: Model name
        temperature: Temperature setting
        max_tokens: Maximum tokens
        
    Returns:
        LlamaIndex BaseLLM instance (LiteLLM)
    """
    provider = provider.lower()
    final_model = model
    
    if provider == "gemini":
        if not final_model.startswith("gemini/"):
            final_model = f"gemini/{final_model}"
    elif provider == "groq":
        if not final_model.startswith("groq/"):
            final_model = f"groq/{final_model}"
            
    return LiteLLM(
        model=final_model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        num_retries=3,
        request_timeout=60.0,
    )
