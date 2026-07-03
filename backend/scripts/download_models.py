import os
import sys
from pathlib import Path
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to pythonpath
sys.path.append(str(Path(__file__).parent.parent))

try:
    from src.config import get_settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    # Try importing fastembed, if available
    try:
        from fastembed import SparseTextEmbedding
    except ImportError:
        logger.warning("fastembed not installed, skipping sparse model download")
        SparseTextEmbedding = None
except ImportError as e:
    logger.error(f"Import error: {e}")
    sys.exit(1)

def download_models():
    """
    Pre-download models during docker build to avoid runtime downloads.
    """
    try:
        settings = get_settings()
        model_name = settings.embedding.model
    except Exception as e:
        logger.warning(f" Could not load full settings (likely due to build-time env vars): {e}")
        logger.warning("Using default embedding model: all-MiniLM-L6-v2")
        model_name = "all-MiniLM-L6-v2"
    logger.info(f"----------------------------------------------------------------")
    logger.info(f"Downloading Dense Model: {model_name}")
    logger.info(f"Target Cache: {os.environ.get('HF_HOME', 'default')}")
    logger.info(f"----------------------------------------------------------------")
    
    try:
        # This triggers the download
        HuggingFaceEmbedding(model_name=model_name)
        logger.info(f"✓ Successfully downloaded {model_name}")
    except Exception as e:
        logger.error(f"❌ Failed to download dense model: {e}")
        sys.exit(1)

    # 2. Download Sparse Model (BM42)
    if SparseTextEmbedding:
        sparse_model_name = "Qdrant/bm42-all-minilm-l6-v2-attentions"
        logger.info(f"----------------------------------------------------------------")
        logger.info(f"Downloading Sparse Model: {sparse_model_name}")
        logger.info(f"Target Cache: {os.environ.get('FASTEMBED_CACHE_PATH', 'default')}")
        logger.info(f"----------------------------------------------------------------")
        
        try:
            # This triggers download
            SparseTextEmbedding(model_name=sparse_model_name)
            logger.info(f"✓ Successfully downloaded {sparse_model_name}")
        except Exception as e:
            logger.error(f"❌ Failed to download sparse model: {e}")
            sys.exit(1)

if __name__ == "__main__":
    download_models()
