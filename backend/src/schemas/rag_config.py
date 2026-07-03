from pydantic import BaseModel, Field
from typing import Literal, Optional

class NotebookRAGConfig(BaseModel):
    """
    User-configurable RAG settings per Notebook.
    Stored in the 'settings' JSONB column of the Notebook table.
    All fields are optional - missing fields fall back to global config defaults.
    """
    # Chunking (for new documents - existing chunks are already indexed)
    chunk_size: Optional[int] = Field(default=None, ge=128, le=2048, description="Size of text chunks")
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=512, description="Overlap between chunks")
    
    # Retrieval
    top_k_results: Optional[int] = Field(default=None, ge=1, le=50, description="Number of chunks to retrieve")
    enable_query_fusion: Optional[bool] = Field(default=None, description="Generate multiple search queries")
    fusion_num_queries: Optional[int] = Field(default=None, ge=1, le=5, description="Number of query variations")
    use_hyde: Optional[bool] = Field(default=None, description="Enable Hypothetical Document Embeddings")
    
    # Hybrid Search
    enable_reranking: Optional[bool] = Field(default=None, description="Enable reranking for better precision")
    reranker_top_n: Optional[int] = Field(default=None, ge=1, le=20, description="Number of chunks after reranking")
    default_alpha: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="0.0 = Keyword, 1.0 = Vector")
    
    # Context
    use_sentence_window: Optional[bool] = Field(default=None, description="Use sentence window for context")
    sentence_window_size: Optional[int] = Field(default=None, ge=1, le=10, description="Sentence window size")
    
    # Synthesis
    response_mode: Optional[Literal["compact", "tree_summarize", "refine"]] = Field(default=None, description="Response synthesis mode")
    streaming: Optional[bool] = Field(default=None, description="Enable streaming responses")
    prompt_style: Optional[Literal["citation", "conversational", "neutral"]] = Field(default=None, description="Prompt style")

    # Confidence / policy thresholds (override global PolicySettings)
    min_score_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Minimum retrieval score for chunk inclusion (0.10 relaxed, 0.25 strict)",
    )
    min_context_chunks: Optional[int] = Field(
        default=None, ge=1, le=10,
        description="Minimum valid chunks required before answering",
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "use_hyde": True,
                "default_alpha": 0.5,
                "prompt_style": "conversational",
                "top_k_results": 10,
                "enable_reranking": True,
                "streaming": True
            }
        }
