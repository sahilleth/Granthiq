# Configuration Reference

Complete environment variables reference for Granthiq Backend.

## Required Variables

### Database

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |

### Supabase

| Variable | Description | Example |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase API URL | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (backend only) | `eyJ...` |
| `SUPABASE_JWT_SECRET` | JWT secret for token validation | `your-jwt-secret` |

### Vector Database

| Variable | Description | Example |
|----------|-------------|---------|
| `QDRANT_HOST` | Qdrant server URL | `https://xxx.cloud.qdrant.io` |
| `QDRANT_API_KEY` | Qdrant API key | `your-api-key` |
| `QDRANT_COLLECTION_NAME` | Collection name | `granthiq` |

### LLM Providers (at least one required)

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GROQ_API_KEY` | Groq API key |
| `COHERE_API_KEY` | Cohere API key (for reranking) |

---

## Optional Variables

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Environment: `development`, `production` |
| `DEBUG` | `true` | Enable debug mode |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |
| `ENABLE_RATE_LIMITING` | `true` | Enable API rate limiting |

### Worker

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_EMBEDDED_WORKER` | `true` | Run worker in API process |

### Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_URL` | Same as `SUPABASE_URL` | Storage endpoint URL |
| `STORAGE_BUCKET_NAME` | `notebook-media` | Default bucket name |

### RAG Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG__CHUNK_SIZE` | `1000` | Text chunk size |
| `RAG__CHUNK_OVERLAP` | `200` | Chunk overlap |
| `RAG__CHUNKING_STRATEGY` | `auto` | Strategy: `semantic`, `token`, `auto` |
| `RAG__TOP_K_RESULTS` | `30` | Number of chunks to retrieve |
| `RAG__ENABLE_RERANKING` | `true` | Enable Cohere reranking |
| `RAG__RERANKER_TOP_N` | `10` | Chunks to rerank |
| `RAG__DEFAULT_ALPHA` | `0.7` | Hybrid search alpha (semantic vs keyword) |
| `RAG__USE_HYDE` | `true` | Enable HyDE for better retrieval |
| `RAG__ENABLE_QUERY_FUSION` | `true` | Enable query expansion |

### LLM Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM__PROVIDER` | `gemini` | Default provider: `gemini`, `openai`, `groq` |
| `LLM__MODEL` | `gemini-2.5-flash` | Model name |
| `LLM__TEMPERATURE` | `0.7` | Generation temperature |
| `LLM__MAX_TOKENS` | `2048` | Max output tokens |

### Policy Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `POLICY__MIN_SCORE_THRESHOLD` | `0.10` | Minimum similarity score |
| `POLICY__MIN_CONTEXT_CHUNKS` | `1` | Minimum chunks required |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | - | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | - | Langfuse secret key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host |
| `LANGFUSE_ENABLED` | `true` | Enable Langfuse tracing |

### External Services

| Variable | Description |
|----------|-------------|
| `FIRECRAWL_API_KEY` | Firecrawl API key (web scraping) |
| `ASSEMBLYAI_API_KEY` | AssemblyAI API key (audio transcription) |

### Google Services

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth2 Client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth2 Client Secret |
| `GOOGLE_REDIRECT_URI` | OAuth2 Redirect URI (e.g., `http://localhost:3000`) |

### SMTP Settings (Resend)

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | `smtp.resend.com` | SMTP Host |
| `SMTP_PORT` | `465` | SMTP Port |
| `SMTP_USER` | `resend` | SMTP User |
| `SMTP_PASSWORD` | - | Resend API Key |
| `SMTP_FROM_EMAIL` | `noreply@memellm.xyz` | Sender Email |
| `SMTP_FROM_NAME` | `Granthiq` | Sender Name |

---

## Example Configuration

### Development (.env)

```env
ENVIRONMENT=development
DEBUG=true

DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/granthiq

SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-key
SUPABASE_JWT_SECRET=your-secret

QDRANT_HOST=http://localhost:6333
QDRANT_COLLECTION_NAME=granthiq

GEMINI_API_KEY=your-gemini-key
COHERE_API_KEY=your-cohere-key

CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Production (.env.production)

```env
ENVIRONMENT=production
DEBUG=false

DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db?ssl=require

SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-key
SUPABASE_JWT_SECRET=your-secret

QDRANT_HOST=https://xxx.cloud.qdrant.io
QDRANT_API_KEY=your-key
QDRANT_COLLECTION_NAME=granthiq

GEMINI_API_KEY=your-key
COHERE_API_KEY=your-key

CORS_ORIGINS=https://app.memellm.xyz
ENABLE_RATE_LIMITING=true

LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_ENABLED=true

# Google Drive
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_REDIRECT_URI=https://app.memellm.xyz

# SMTP
SMTP_FROM_EMAIL=noreply@memellm.xyz
SMTP_FROM_NAME="Granthiq"
SMTP_PASSWORD=re_xxx
```

---

## Configuration Hierarchy

1. Environment variables (highest priority)
2. `.env` file
3. Default values in code

---

## Validation

Configuration is validated at startup. Missing required variables will cause the application to fail with a descriptive error message.

Check configuration:
```bash
python -c "from src.config import get_settings; print(get_settings())"
```
