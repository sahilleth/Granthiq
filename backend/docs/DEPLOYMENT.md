# Deployment Guide

Production deployment instructions for Granthiq Backend.

## Deployment Options

| Platform | Recommended For | Cost |
|----------|-----------------|------|
| Railway | Quick deployment, hobby projects | $5-20/month |
| Coolify | Self-hosted, full control | $4-20/month (VPS) |
| Render | Alternative to Railway | $7-25/month |
| Docker + VPS | Full control, scaling | Variable |

---

## Coolify Deployment (Self-Hosted)

### Prerequisites

1. [Coolify](https://coolify.io) instance (or install on your VPS)
2. Supabase project (database + auth)
3. Qdrant Cloud cluster

### Step 1: Create New Project

1. Go to your Coolify dashboard
2. Click **New Project** → **Create New Project**
3. Give it a name (e.g., "Granthiq")

### Step 2: Add API Service

1. Click **Add New Resource** → **Application**
2. Select your GitHub repository
3. Configure:
   - **Build Pack**: Dockerfile
   - **Dockerfile Path**: `backend/Dockerfile`
   - **Build Target**: `runtime`

### Step 3: Configure Environment Variables

Add these variables in Coolify:

```env
# Database (Required)
DATABASE_URL=postgresql+asyncpg://postgres:[PASSWORD]@[HOST]:5432/postgres?sslmode=require

# Supabase (Required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Vector Database (Required)
QDRANT_HOST=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key

# LLM Provider (At least one required)
GEMINI_API_KEY=your-gemini-key

# Reranking (Required for quality)
COHERE_API_KEY=your-cohere-key

# Security
ENVIRONMENT=production
CORS_ORIGINS=https://your-frontend.com
```

### Step 4: Configure Port & Health Check

- **Port**: `8000`
- **Health Check**: `http://localhost:8000/api/v1/health/liveness`

### Step 5: Add Worker Service

1. Add another Application resource
2. Use same repository and Dockerfile
3. Set **Build Target**: `worker`
4. Override **Command**: `python -m src.services.queue.worker`

### Step 6: Deploy

Click **Deploy** and monitor logs.

---

## Railway Deployment (Recommended)

### Prerequisites

1. [Railway account](https://railway.app)
2. GitHub repository with your code
3. Supabase project (database + auth)
4. Qdrant Cloud cluster

### Step 1: Create Railway Project

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your repository
4. Railway will auto-detect the Dockerfile

### Step 2: Configure Environment Variables

In Railway Dashboard → Your Service → **Variables** tab:

```env
# Database (Required)
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Supabase (Required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Vector Database (Required)
QDRANT_HOST=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION_NAME=granthiq

# LLM Provider (At least one required)
GEMINI_API_KEY=your-gemini-key

# Reranking (Required for quality)
COHERE_API_KEY=your-cohere-key

# Security (Required for production)
ENVIRONMENT=production
CORS_ORIGINS=https://your-frontend.com

# Observability (Optional)
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Step 3: Deploy

Railway auto-deploys on push. Check logs in the **Deployments** tab.

### Step 4: Verify

```bash
curl https://your-app.up.railway.app/health
```

---

## Docker Deployment

### Build Image

```bash
cd backend
docker build -t granthiq-backend .
```

### Run Container

```bash
docker run -d \
  --name granthiq \
  -p 8000:8000 \
  --env-file .env.production \
  granthiq-backend
```

### Docker Compose

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env.production
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Architecture Modes

### Combined Mode (Default)

API server and background worker run in the same process. Cost-effective for hobby projects.

```env
ENABLE_EMBEDDED_WORKER=true  # Default
```

### Separate Mode (Scalable)

For high traffic, deploy API and worker as separate services:

```env
# On API service:
ENABLE_EMBEDDED_WORKER=false
```

Deploy worker using Dockerfile target `worker`.

---

## Database Setup

### Supabase (Recommended)

1. Create project at [supabase.com](https://supabase.com)
2. Get connection string: **Settings** → **Database** → **Connection String**
3. Format: `postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres`

### Initialize Tables

```bash
python -m scripts.setup_db
```

---

## Vector Database (Qdrant)

### Qdrant Cloud

1. Create cluster at [cloud.qdrant.io](https://cloud.qdrant.io)
2. Configure:
   ```env
   QDRANT_HOST=https://xxx.cloud.qdrant.io
   QDRANT_API_KEY=your-api-key
   ```

---

## Health Checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Full system health |
| `GET /health/liveness` | Liveness probe |
| `GET /health/readiness` | Readiness probe |

---

## Monitoring

### Langfuse

```env
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_ENABLED=true
```

Traces all LLM calls, retrievals, and generations.

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common deployment issues.
