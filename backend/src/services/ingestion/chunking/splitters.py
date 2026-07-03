from typing import List, Optional, Literal, Union
from llama_index.core.node_parser import (
    SentenceSplitter,
    TokenTextSplitter,
    SemanticSplitterNodeParser,
    MarkdownNodeParser,
    CodeSplitter,
    HierarchicalNodeParser,
)
from loguru import logger

def get_advanced_splitter(
    strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto", "hierarchical"] = "auto",
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    embed_model=None,
    source_type: Optional[str] = None,
    filename: Optional[str] = None,
    hierarchical_chunk_sizes: Optional[List[int]] = None,
) -> Union[SentenceSplitter, TokenTextSplitter, HierarchicalNodeParser]:
    """
    Get an appropriate splitter based on strategy and document type.
    """
  
    if strategy == "hierarchical":
        chunk_sizes = hierarchical_chunk_sizes or [2048, 1024, 512]
        min_chunk_size = min(chunk_sizes)
        adjusted_overlap = min(chunk_overlap, min_chunk_size // 4)
        if adjusted_overlap < 0:
            adjusted_overlap = 0
        
        return HierarchicalNodeParser.from_defaults(
            chunk_sizes=chunk_sizes,
            chunk_overlap=adjusted_overlap,
        )
    
  
    if strategy == "auto":
        file_ext = ""
        if filename:
            file_ext = filename.lower()
        elif source_type:
            file_ext = str(source_type).lower()
        
        if ".md" in file_ext or "markdown" in file_ext:
            strategy = "markdown" 
        elif any(ext in file_ext for ext in [".py", ".js", ".java", ".cpp", ".c", ".go", ".rs", ".ts"]):
            strategy = "code" 
        elif embed_model is not None:
            strategy = "semantic"
        else:
            strategy = "sentence"
    
  
    if strategy == "semantic":
        # CRITICAL: SemanticSplitterNodeParser requires embed_model
        # If None, it will try to use OpenAI as fallback, which we don't want
        if embed_model is None:
            logger.warning(
                "Semantic chunking requested but embed_model is None. "
                "Falling back to sentence splitting to avoid OpenAI fallback."
            )
            return SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separator=" ",
                include_metadata=True,
                include_prev_next_rel=True,
            )
        
        return SemanticSplitterNodeParser(
            buffer_size=1,
            breakpoint_percentile_threshold=95,
            embed_model=embed_model,
            include_metadata=True,
            include_prev_next_rel=True,
        )
    
    if strategy == "token":
        return TokenTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=" ",
            include_metadata=True,
            include_prev_next_rel=True,
        )
    elif strategy == "markdown":
        return MarkdownNodeParser(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            include_metadata=True,
            include_prev_next_rel=True,
        )
    elif strategy == "code":
        language = "python"  
        if filename:
            ext_to_lang = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".java": "java", ".cpp": "cpp", ".c": "c",
                ".go": "go", ".rs": "rust", ".rb": "ruby",
            }
            for ext, lang in ext_to_lang.items():
                if ext in filename.lower():
                    language = lang
                    break
        
        return CodeSplitter(
            language=language,
            chunk_lines=40,
            chunk_lines_overlap=10,
            include_metadata=True,
            include_prev_next_rel=True,
        )
    else:
        return SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=" ",
            include_metadata=True,
            include_prev_next_rel=True,
        )

