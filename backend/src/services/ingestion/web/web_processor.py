import sys
from pathlib import Path


from dotenv import load_dotenv
load_dotenv()
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid
from urllib.parse import urlparse
from loguru import logger
from dataclasses import dataclass

from src.utils.exceptions import DocumentProcessingError
from src.schemas.document import UnifiedDocument, DocumentType, ProcessingStatus
from src.services.ingestion.chunk_manager import apply_chunking_to_document_non_destructive
from src.services.embeddings.embedding_config import get_llamaindex_embed_model, configure_llamaindex_embed_model
from firecrawl import Firecrawl
from src.config import get_settings

if __name__ == "__main__":
    get_settings.cache_clear()

@dataclass
class WebPageData:
    """Represents scraped web page data with additional metadata"""
    url: str
    title: str
    content: str
    metadata: Dict[str, Any]
    success: bool
    error: Optional[str] = None


class WebProcessor:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.firecrawl.api_key
        
        if not self.api_key:
            import os
            # Check both possible environment variable names
            env_key = os.getenv("FIRECRAWL__API_KEY") or os.getenv("FIRECRAWL_API_KEY")
            if env_key:
                logger.warning(f"API key found in environment but not loaded from config. Using environment variable.")
                self.api_key = env_key
            else:
                raise ValueError(
                    "Firecrawl API key is required. Set FIRECRAWL__API_KEY environment variable "
                    "(with double underscore) or FIRECRAWL_API_KEY in your .env file."
                )
        
        self.firecrawl = Firecrawl(api_key=self.api_key)
        logger.info("WebProcessor initialized successfully")

    def process_url(self, url: str) -> UnifiedDocument:
        try:
            logger.info(f"Processing URL: {url}")
            if not self._is_valid_url(url):
                raise DocumentProcessingError(f"Invalid URL: {url}")

            scrape_params = {
                'formats': ['markdown', 'html'],
                'timeout': 30000
            }
            response = self.firecrawl.scrape(url, **scrape_params)
            page_data = self._process_response(response, url)
            if not page_data.success or not page_data.content:
                raise DocumentProcessingError(page_data.error or "Empty content")

            now = datetime.now(timezone.utc)
            settings = get_settings()
            doc = UnifiedDocument(
                id=uuid.uuid4(),
                user_id=settings.anonymous_user_id,  # caller can reassign if needed
                filename=page_data.title or urlparse(url).path or urlparse(url).netloc,
                source_type=DocumentType.WEB,
                status=ProcessingStatus.COMPLETED,
                storage_path=url,
                created_at=now,
                updated_at=now,
                metadata=page_data.metadata,
            )

            base_sections = self._split_markdown_sections(page_data.content)
            for idx, section in enumerate(base_sections):
                if not section.strip():
                    continue
                doc.add_chunk(
                    content=section,
                    chunk_index=idx,
                    page_number=None,
                    metadata={
                        "source": "web",
                        "source_id": page_data.metadata.get("domain"),
                        "source_url": url,
                        "section": idx,
                        "title": page_data.title,
                        "language": page_data.metadata.get("language", "en"),
                        "domain": page_data.metadata.get("domain"),
                    },
                )

           
            overlap = max(0, min(settings.rag.chunk_overlap, settings.rag.chunk_size // 2))
            chunking_strategy = settings.rag.chunking_strategy
            embed_model = None
            
            if chunking_strategy == "semantic" or chunking_strategy == "auto":
                try:
                    
                    embed_model = get_llamaindex_embed_model()
                    if embed_model is None:
                        configure_llamaindex_embed_model()
                        embed_model = get_llamaindex_embed_model()
                except (ImportError, RuntimeError, ValueError) as e:
                    logger.warning(f"Failed to load embedding model for semantic chunking: {e}. Falling back to sentence chunking.")
                    chunking_strategy = "sentence"
                    embed_model = None
            
            doc = apply_chunking_to_document_non_destructive(
                doc,
                chunk_size=settings.rag.chunk_size,
                chunk_overlap=overlap,
                respect_sentence_boundary=True,
                strategy=chunking_strategy,
                embed_model=embed_model,
            )

            logger.info(f"Processed {doc.chunk_count} chunks for URL: {url}")
            return doc
        except Exception as e:
            logger.error(f"Failed to process URL: {url}", exc_info=True)
            raise DocumentProcessingError(f"Failed to process URL: {url}") from e

    def _process_response(self, result: Any, url: str) -> WebPageData:
        """
        Process Firecrawl response which can be either a dict or a Document object.
        """
        try:
            if not isinstance(result, dict):
                if hasattr(result, 'model_dump'):
                    result = result.model_dump()
                elif hasattr(result, 'dict'):
                    result = result.dict()
                elif hasattr(result, '__dict__'):
                    result = {k: v for k, v in result.__dict__.items() if not k.startswith('_')}
                else:
                    result = {
                        'markdown': getattr(result, 'markdown', None) or getattr(result, 'content', ''),
                        'title': getattr(result, 'title', ''),
                        'metadata': getattr(result, 'metadata', {})
                    }
            
            content = result.get('markdown', '') or result.get('content', '')
            metadata_dict = result.get('metadata', {})
            
            if not isinstance(metadata_dict, dict):
                if hasattr(metadata_dict, 'model_dump'):
                    metadata_dict = metadata_dict.model_dump()
                elif hasattr(metadata_dict, 'dict'):
                    metadata_dict = metadata_dict.dict()
                elif hasattr(metadata_dict, '__dict__'):
                    metadata_dict = {k: v for k, v in metadata_dict.__dict__.items() if not k.startswith('_')}
                else:
                    metadata_dict = {}
            
            title = metadata_dict.get('title', '') or result.get('title', '')
            
            metadata = {
                'scraped_at': datetime.now().isoformat(),
                'original_url': url,
                'title': title,
                'description': metadata_dict.get('description', ''),
                'keywords': metadata_dict.get('keywords', []),
                'language': metadata_dict.get('language', 'en'),
                'word_count': len(content.split()) if content else 0,
                'character_count': len(content) if content else 0,
                'domain': urlparse(url).netloc
            }
            
            return WebPageData(
                url=url,
                title=title,
                content=content,
                metadata=metadata,
                success=True,
                error=None
            )
        except Exception as e:
            logger.error(f"Error processing Firecrawl response: {e}", exc_info=True)
            return WebPageData(
                url=url,
                title='',
                content='',
                metadata={},
                success=False,
                error=str(e)
            )

    def _is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
       
            if result.scheme not in ('http', 'https'):
                return False
          
            if not result.netloc:
                return False
            return True
        except (ValueError, TypeError) as e:
            logger.debug(f"URL validation failed for '{url}': {e}")
            return False

    def _split_markdown_sections(self, md: str) -> List[str]:
        """
        Split markdown into logical sections using heading markers.
        Falls back to paragraph splitting if no headings present.
        """
        if not md or not md.strip():
            return []

        lines = md.splitlines()
        sections: List[str] = []
        current: List[str] = []

        def flush():
            if current and any(s.strip() for s in current):
                sections.append("\n".join(current).strip())

        for line in lines:
            if line.lstrip().startswith(('# ', '## ', '### ', '#### ', '##### ', '###### ')) and current:
                flush()
                current = [line]
            else:
                current.append(line)
        flush()

        if not sections:
            # Fallback: split by double newlines (paragraphs)
            sections = [p.strip() for p in md.split("\n\n") if p.strip()]

        return sections



if __name__ == "__main__":
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    processor = WebProcessor()
    doc = processor.process_url("https://www.docling.ai/")
    print(doc)