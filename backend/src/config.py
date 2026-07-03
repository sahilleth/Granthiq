from __future__ import annotations
from functools import lru_cache
from typing import List, Literal, Optional, Union
from loguru import logger
import uuid
import os
from pydantic import BaseModel, Field, field_validator, ValidationInfo, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

def setup_google_credentials():
    """
    Helper to handle Google Credentials in containerized environments.
    allows passing the JSON content directly via GOOGLE_APPLICATION_CREDENTIALS_JSON
    instead of determining a file path.
    """
    import json
    import tempfile
    
    cred_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    cred_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    # If we have the JSON string but no file (or file doesn't exist), create it
    if cred_json and (not cred_file or not os.path.exists(cred_file)):
        try:
            logger.info("Detected GOOGLE_APPLICATION_CREDENTIALS_JSON, writing to temporary file...")
            
            # Use a slightly more persistent path than pure tempfile if possible, 
            # or just a standard temp location. 
            # We'll use the temp directory but with a fixed name to avoid spamming 
            # if this runs multiple times (though it shouldn't).
            target_path = os.path.join(tempfile.gettempdir(), "google_credentials.json")
            
            # Handle potential base64 encoding (common in some secret managers)
            if not cred_json.strip().startswith("{"):
                import base64
                try:
                    decoded = base64.b64decode(cred_json).decode('utf-8')
                    cred_json = decoded
                except Exception:
                    pass # Assume it was just a raw string if decode fails

            with open(target_path, "w") as f:
                f.write(cred_json)
            
            # Set the env var so Google libraries find it
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = target_path
            logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to {target_path}")
            
        except Exception as e:
            logger.error(f"Failed to process Google Credentials JSON: {e}")

# Run setup immediately
setup_google_credentials()

# --- Security & Storage ---
class AuthSettings(BaseModel):
    enabled: bool = Field(default=True, description="Enable JWT authentication")
    algorithm: str = Field(default="ES256", description="JWT algorithm (ES256/RS256 via JWKS)")
    supabase_url: str = Field(default=os.getenv("SUPABASE_URL"), description="Project API URL for JWKS")
    access_token_expire_minutes: int = Field(default=43200)

class StorageSettings(BaseModel):
    # Default to supabase storage for production use
    provider: Literal["local", "s3", "supabase"] = Field(
        default="supabase",
        description="Storage provider: 'supabase' for Supabase Storage (recommended)"
    )
    bucket_name: str = Field(default=os.getenv("STORAGE_BUCKET_NAME", "notebook-media"))
    
    # Provider-specific file size limits (in MB)
    # Supabase free tier: 50MB per file limit
    # Cloudflare R2 / Backblaze B2 / S3: No per-file limit on free tier (default 100MB, configurable)
    max_file_size_mb: int = Field(
        default=50,  # Default for Supabase free tier limit
        description="Maximum file size in MB. Supabase free tier: 50MB, S3/R2/B2: configurable (default 100MB)"
    )
    
    # S3 / Supabase Credentials
    endpoint_url: Optional[str] = Field(default=os.getenv("STORAGE_ENDPOINT_URL"))
    access_key: Optional[str] = Field(default=os.getenv("AWS_ACCESS_KEY_ID"))
    secret_key: Optional[str] = Field(default=os.getenv("AWS_SECRET_ACCESS_KEY"))
    region: str = Field(default=os.getenv("AWS_REGION", "us-east-1"))

    # Supabase Specific
    # Note: SUPABASE_URL should be the API URL (https://xxx.supabase.co), not the database connection string
    # For database, use DATABASE_URL which should be the PostgreSQL connection string
    # Example: https://sxriayklgpuwehizxflq.supabase.co
    supabase_url: Optional[str] = Field(
        default=os.getenv("STORAGE_URL"),
        description="Supabase API URL (https://xxx.supabase.co), not database connection string"
    )
    supabase_key: Optional[str] = Field(default=os.getenv("SUPABASE_KEY")) # New sb_secret_... key (replaces legacy service_role JWT)
    public_bucket: str = Field(default="notebook-public", description="For Podcasts/Audio")
    private_bucket: str = Field(default="notebook-private", description="For Documents")

# --- Infrastructure ---
class ApiSettings(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: Union[List[str], str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins. Set via CORS_ORIGINS environment variable (comma-separated or JSON array)"
    )
    enable_rate_limiting: bool = Field(
        default=True,
        description="Enable rate limiting on API endpoints"
    )

    @field_validator("cors_origins", mode="before")
    def parse_cors_origins(cls, v: object, info: ValidationInfo) -> List[str]:
        """
        Accept JSON list string, comma-separated string, or list.

        Security: Blocks wildcard (*) origins in production environment.
        """
        if v is None:
            return ["http://localhost:3000", "http://localhost:5173"]
        if isinstance(v, list):
            origins = [str(x) for x in v]
        else:
            s = str(v).strip()
            # Handle escaped quotes commonly found in environment variables
            if r'\"' in s:
                s = s.replace(r'\"', '"')

            if s.startswith("[") and s.endswith("]"):
                try:
                    import json
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        origins = [str(x) for x in parsed]
                    else:
                        # Fallback for non-list JSON (shouldn't happen with valid JSON array)
                        origins = [str(parsed)]
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(f"Could not parse CORS origins as JSON: {s}, error: {e}")
                    # Robust fallback: strip brackets, split by comma, then strip quotes/whitespace
                    origins = [part.strip().strip("'\"") for part in s[1:-1].split(",") if part.strip()]
            else:
                origins = [part.strip() for part in s.split(",") if part.strip()]

        # Block wildcard in production
        environment = os.getenv("ENVIRONMENT", "development")
        if environment == "production" and "*" in origins:
            raise ValueError(
                "CORS wildcard ('*') is not allowed in production environment. "
                "Please specify exact allowed origins in API__CORS_ORIGINS. "
                "Example: API__CORS_ORIGINS=https://app.example.com,https://api.example.com"
            )

        return origins

class DatabaseSettings(BaseModel):
    url: Optional[str] = Field(default=None)  # Will be set by field_validator in Settings
    echo: bool = Field(default=False)

class QdrantSettings(BaseModel):
    host: str = Field(default=os.getenv("QDRANT_HOST"))
    api_key: Optional[str] = Field(default=os.getenv("QDRANT_API_KEY"))
    collection_name: str = Field(default=os.getenv("QDRANT_COLLECTION_NAME") or "notebookllm")

# --- AI Services ---
class LlmSettings(BaseModel):
    model_config = {"protected_namespaces": ()}  # Allow model_name field

    provider: Literal["groq", "gemini", "openai"] = Field(default="gemini")
    model_name: str = Field(default="gemini-2.5-flash")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=8192)

    groq_api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    cohere_api_key: Optional[str] = os.getenv("COHERE_API_KEY")

class EmbeddingSettings(BaseModel):
    model: str = Field(default="all-MiniLM-L6-v2")
    dimension: int = Field(default=384)

class FirecrawlSettings(BaseModel):
    api_key: Optional[str] = Field(default=os.getenv("FIRECRAWL_API_KEY"))

class AssemblyAISettings(BaseModel):
    api_key: Optional[str] = Field(default=os.getenv("ASSEMBLYAI_API_KEY"))

class SarvamSettings(BaseModel):
    api_key: Optional[str] = Field(default=os.getenv("SARVAM_API_KEY"))

class GoogleSettings(BaseModel):
    """Google OAuth2 and Drive API settings."""
    client_id: Optional[str] = Field(default=os.getenv("GOOGLE_CLIENT_ID"))
    client_secret: Optional[str] = Field(default=os.getenv("GOOGLE_CLIENT_SECRET"))
    redirect_uri: str = Field(default=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/sources/google/auth/callback"))
    scopes: List[str] = Field(
        default_factory=lambda: [
            "https://www.googleapis.com/auth/drive.readonly",
        ],
        description="OAuth scopes for Google Drive access"
    )

class EmailSettings(BaseModel):
    enabled: bool = Field(default=os.getenv("EMAIL_ENABLED", "false").lower() == "true")
    smtp_host: str = Field(default=os.getenv("SMTP_HOST", "smtp.example.com"))
    smtp_port: int = Field(default=int(os.getenv("SMTP_PORT", "587")))
    smtp_user: Optional[str] = Field(default=os.getenv("SMTP_USER"))
    smtp_password: Optional[str] = Field(default=os.getenv("SMTP_PASSWORD"))
    from_email: str = Field(default=os.getenv("SMTP_FROM_EMAIL", "noreply@example.com"))
    from_name: str = Field(default=os.getenv("SMTP_FROM_NAME", "Lumina"))
    tls: bool = Field(default=True)

# --- RAG Defaults (Overridable per Notebook) ---
class RagSettings(BaseModel):
    chunk_size: int = Field(default=1000, ge=1)
    chunk_overlap: int = Field(default=200, ge=0)
    chunking_strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto"] = Field(
        default="auto",
        description="Chunking strategy: 'semantic' for semantic similarity, 'token' for token-based, 'sentence' for sentence-based, 'auto' for intelligent selection"
    )
    top_k_results: int = Field(default=15, ge=1)  # Balanced: good recall + fast processing
    
    # Query Fusion Settings
    enable_query_fusion: bool = Field(default=True, description="Enable Reciprocal Rerank Fusion for query expansion")
    fusion_num_queries: int = Field(default=4, ge=1, le=10, description="Number of query variations to generate (1 = disabled)")
    fusion_mode: Literal["reciprocal_rerank", "rrf"] = Field(default="reciprocal_rerank", description="Fusion algorithm mode")
    
    # HyDE (Hypothetical Document Embeddings)
    use_hyde: bool = Field(default=True, description="Enable HyDE for improved retrieval on vague/abstract queries")  # Based on A/B testing: +5.8% improvement
    
    # Hybrid Search Defaults
    enable_reranking: bool = Field(default=True, description="Enable reranking of search results")
    reranker_top_n: int = Field(default=10, description="Number of top results to rerank")  # FIXED: Increased from 5 to 10
    reranker_type: Literal["cohere"] = Field(default="cohere", description="Reranker type (currently only 'cohere' supported)")
    default_alpha: float = Field(default=0.7, description="Hybrid search alpha (0.7 = Favors Semantic)")
    
    # MMR (Maximum Marginal Relevance) Settings
    enable_mmr: bool = Field(default=False, description="Enable Maximum Marginal Relevance for diversity in results")
    mmr_diversity: float = Field(default=0.5, description="MMR diversity threshold (0.0 = relevance only, 1.0 = diversity only)")
    
    # Context Enhancement
    use_sentence_window: bool = Field(default=True, description="Enable sentence window for context expansion")
    sentence_window_size: int = Field(default=3, description="Number of sentences to include around retrieved chunks")
    
    # Response Generation
    # COMPACT mode: Summarizes all context in single LLM call (FAST - recommended for production)
    # REFINE mode: Iteratively processes chunks (SLOW - multiple LLM calls, 2-3 min per response)
    response_mode: Literal["compact", "compact_accumulate", "refine", "tree_summarize", "simple_summarize", "accumulate", "generation", "no_text"] = Field(default="compact", description="Response mode: 'compact' for fast responses (recommended), 'refine' for more detailed but slower responses")
    streaming: bool = Field(default=True, description="Enable streaming responses")
    prompt_style: str = Field(default="notebooklm", description="Prompt style: 'notebooklm' (detailed + citations), 'citation', 'conversational', 'comprehensive'")

# --- Upload Settings ---
class UploadSettings(BaseModel):
    max_size_mb: int = Field(default=100, ge=1)
    allowed_extensions: List[str] = Field(
        default_factory=lambda: [".ipynb", ".py", ".md", ".txt", ".pdf"]
    )

    @field_validator("allowed_extensions", mode="before")
    def parse_extensions(cls, v: object) -> List[str]:
        if v is None:
            return [".ipynb", ".py", ".md", ".txt", ".pdf"]
        if isinstance(v, list):
            return [ext if ext.startswith(".") else f".{ext}" for ext in v]
        s = str(v).strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [
                        ext if str(ext).startswith(".") else f".{ext}"
                        for ext in parsed
                    ]
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Could not parse upload extensions as JSON: {s}, error: {e}")
        return [
            ext if ext.startswith(".") else f".{ext}"
            for ext in [part.strip() for part in s.split(",") if part.strip()]
        ]

# --- Observability ---
class LangfuseSettings(BaseModel):
    public_key: Optional[str] = Field(default=os.getenv("LANGFUSE_PUBLIC_KEY"))
    secret_key: Optional[str] = Field(default=os.getenv("LANGFUSE_SECRET_KEY"))
    host: str = Field(default=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"))
    enabled: bool = Field(default=os.getenv("LANGFUSE_ENABLED", "true").lower() == "true")

class SentrySettings(BaseModel):
    dsn: Optional[str] = Field(default=os.getenv("SENTRY_DSN"))
    environment: str = Field(default=os.getenv("ENVIRONMENT", "development"))
    traces_sample_rate: float = Field(default=1.0)
    profiles_sample_rate: float = Field(default=1.0)

    @field_validator("dsn", mode="after")
    @classmethod
    def validate_sentry_dsn(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        """Validate that Sentry DSN is present in production."""
        # Get environment from the parent settings context or default
        environment = os.getenv("ENVIRONMENT", "development")
        
        if environment == "production" and not v:
            logger.warning(
                "SENTRY_DSN is not configured in production environment. "
                "Error tracking will be disabled. Set SENTRY_DSN environment variable to enable."
            )
        return v

class EvaluationSettings(BaseModel):
    enabled: bool = Field(default=True)
    online_evaluation: bool = Field(default=True)
    evaluation_sampling_rate: float = Field(default=0.2) # Sample 20% of queries
    log_scores_to_langfuse: bool = Field(default=True)
    metrics: List[str] = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]

# --- Policy Settings ---
class PolicySettings(BaseModel):
    # CRITICAL: This threshold is for SIMILARITY SCORES (0.1-0.5 range), NOT reranker scores (0.7-0.9)!
    # For all-MiniLM-L6-v2, scores >0.30 are strong matches. Financial/domain content may score 0.15-0.30.
    min_score_threshold: float = Field(default=0.10, description="Minimum similarity score (0.0-1.0) for chunk inclusion. 0.15 = balanced, 0.10 = relaxed, 0.25 = strict")
    min_context_chunks: int = Field(default=1, description="Minimum number of valid chunks required to attempt an answer")
    hyde_timeout: float = Field(default=2.0, description="Max seconds to wait for HyDE generation before skipping")
    refusal_message: str = Field(default="I'm sorry, but I don't have enough relevant information in the provided documents to answer that question accurately.", description="Standard refusal message")

# --- Main Settings ---
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    app_name: str = "Granthiq"
    debug: bool = False
    environment: str = "development"
    # Security fallback for dev
    anonymous_user_id: uuid.UUID = Field(default_factory=uuid.uuid4)

    api: ApiSettings = Field(default_factory=lambda: ApiSettings())
    auth: AuthSettings = Field(default_factory=AuthSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    
    llm: LlmSettings = Field(default_factory=LlmSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    
    rag: RagSettings = Field(default_factory=RagSettings)
    upload: UploadSettings = Field(default_factory=UploadSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    
    # Third-party Services
    firecrawl: FirecrawlSettings = Field(default_factory=FirecrawlSettings)
    assemblyai: AssemblyAISettings = Field(default_factory=AssemblyAISettings)
    sarvam: SarvamSettings = Field(default_factory=SarvamSettings)
    google: GoogleSettings = Field(default_factory=GoogleSettings)
    
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    sentry: SentrySettings = Field(default_factory=SentrySettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)

    @field_validator("database", mode="before")
    @classmethod
    def assemble_db_connection(cls, v, info: ValidationInfo):
        """
        Handle both flat DATABASE_URL (Railway/Render) and nested DATABASE__URL (Pydantic default).
        Also converts postgresql:// to postgresql+asyncpg:// for async SQLAlchemy.
        """
        from typing import Dict, Any

        def convert_db_url(url: str) -> str:
            """Convert postgresql:// to postgresql+asyncpg:// if needed."""
            if url and url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url

        # 1. Check if the flat env var exists (Railway/cloud platforms set this)
        env_db_url = os.getenv("DATABASE_URL")

        # 2. If it exists, override whatever Pydantic found
        if env_db_url:
            converted_url = convert_db_url(env_db_url)
            if isinstance(v, dict):
                v["url"] = converted_url
                return v
            # If v is None or default, create new DatabaseSettings with the URL
            return {"url": converted_url, "echo": False}

        # 3. Fallback to default logic (local dev with .env file)
        if v is None:
            return DatabaseSettings()

        # 4. Also convert URL if v is a dict with url key (from nested env vars)
        if isinstance(v, dict) and v.get("url"):
            v["url"] = convert_db_url(v["url"])

        return v

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
