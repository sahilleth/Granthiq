from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration for LLM instances."""
    
    api_key: str = Field(..., description="API key for the LLM provider")
    model: str = Field(..., description="Model name")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="Maximum tokens to generate")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0, description="Top-p sampling parameter")
    streaming: bool = Field(default=False, description="Enable streaming responses")
    verbose: bool = Field(default=False, description="Enable verbose logging")
    extra_params: Dict[str, Any] = Field(default_factory=dict, description="Additional parameters")


class LLMResponse(BaseModel):
    """Response from LLM generation."""
    
    content: str = Field(..., description="Generated text content")
    model: str = Field(..., description="Model used for generation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    def __str__(self) -> str:
        return self.content


class LLMProvider(BaseModel):
    """LLM provider information."""
    
    name: Literal["groq", "gemini", "openai"] = Field(..., description="Provider name")
    api_key: str = Field(..., description="API key")
    default_model: str = Field(..., description="Default model for this provider")
    
    class Config:
        frozen = True

