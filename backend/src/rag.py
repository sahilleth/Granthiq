from src.services.query.query_engine import get_query_engine
from src.services.retriever.factory import get_retriever
from src.services.ingestion.factory import get_main_processor
from src.services.llm.factory import create_llamaindex_llm

from src.services.indexer.indexer import get_indexer
from src.config import get_settings
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

def get_rag_pipeline():
    settings = get_settings()
    query_engine = get_query_engine()
    main_processor = get_main_processor()

    # Create LLMs first (needed for retriever)
    groq_llm = None
    if settings.llm.groq_api_key:
        try:
            groq_llm = create_llamaindex_llm(
                provider="groq",
                api_key=settings.llm.groq_api_key,
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=2048
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Groq LLM: {e}")
    else:
        logger.warning("GROQ_API_KEY not found. Groq LLM will not be available.")
    
    gemini_llm = None
    if settings.llm.gemini_api_key:
        try:
            gemini_llm = create_llamaindex_llm(
                provider="gemini",
                api_key=settings.llm.gemini_api_key,
                model="gemini-2.5-flash",
                temperature=0.7,
                max_tokens=2048
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini LLM: {e}. Make sure GEMINI_API_KEY is set correctly.")
        
    openai_llm = None
    if settings.llm.openai_api_key:
        try:
            openai_llm = create_llamaindex_llm(
                provider="openai",
                api_key=settings.llm.openai_api_key,
                model=settings.llm.model_name,
                temperature=0.7,
                max_tokens=2048
            )
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI LLM: {e}. Make sure OPENAI_API_KEY is set correctly.")

    # Create retriever with the first available LLM (required for thread safety)
    primary_llm = groq_llm or gemini_llm or openai_llm
    if primary_llm:
        retriever = get_retriever(llm=primary_llm)
    else:
        logger.error("No LLM available for retriever - at least one API key is required")
        retriever = None

    indexer = get_indexer()
    return query_engine, retriever, main_processor, groq_llm, gemini_llm, openai_llm, indexer
