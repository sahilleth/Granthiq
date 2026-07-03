# Setup Guide

Complete step-by-step guide to set up the Granthiq Backend on your local machine.

**Time Required:** ~20 minutes  
**Difficulty:** Intermediate  
**Prerequisites:** Basic knowledge of Python, PostgreSQL, and command line

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Supabase Setup](#1-supabase-setup)
3. [Qdrant Setup](#2-qdrant-setup)
4. [Backend Installation](#3-backend-installation)
5. [Environment Configuration](#4-environment-configuration)
6. [Database Initialization](#5-database-initialization)
7. [Running the Application](#6-running-the-application)
8. [Verification](#7-verification)
9. [Troubleshooting](#8-troubleshooting)
10. [Next Steps](#9-next-steps)

---

## Prerequisites

Before starting, ensure you have the following installed:

### Required Software

| Software | Version | Download |
|----------|---------|----------|
| **Python** | 3.12+ | [python.org](https://www.python.org/downloads/) |
| **Git** | Latest | [git-scm.com](https://git-scm.com/) |
| **Docker** | Latest (for Qdrant) | [docker.com](https://www.docker.com/get-started) |

### Required Accounts

- **Supabase Account** - [supabase.com](https://supabase.com) (Free tier available)
- **Google AI Studio** - [aistudio.google.com](https://aistudio.google.com/) (for Gemini API key)
- **Qdrant Cloud** (Optional) - [cloud.qdrant.io](https://cloud.qdrant.io/) (Free tier available)

### Optional Accounts

- **Cohere** - [cohere.com](https://cohere.com/) (for reranking, recommended)
- **Langfuse** - [langfuse.com](https://langfuse.com/) (for observability)
- **Groq** - [groq.com](https://groq.com/) (for faster inference)
- **OpenAI** - [openai.com](https://platform.openai.com/) (alternative LLM)

---

## 1. Supabase Setup

Supabase provides PostgreSQL database, authentication, and storage.

### Step 1.1: Create a Supabase Project

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard)
2. Click **"New Project"**
3. Fill in project details:
   - **Name**: `granthiq-backend` (or any name)
   - **Database Password**: Generate a strong password ⚠️ **Save this!**
   - **Region**: Choose closest to you
   - **Pricing Plan**: Free (for development)
4. Click **"Create new project"**
5. Wait 2-3 minutes for project setup

### Step 1.2: Get Database Connection String

1. In your Supabase dashboard, go to **Settings** → **Database**
2. Scroll down to **Connection String** section
3. Select **URI** tab
4. Copy the connection string (it looks like):
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.xxx.supabase.co:5432/postgres
   ```
5. **Important**: Replace `[YOUR-PASSWORD]` with your actual database password
6. **For our app**: Change the prefix to use asyncpg:
   ```
   postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.xxx.supabase.co:5432/postgres?ssl=require
   ```
7. Save this for later (you'll add it to `.env` file)

### Step 1.3: Get API Credentials

1. Go to **Settings** → **API**
2. Copy the following values:

| Field | Where to use | Example |
|-------|--------------|---------|
| **Project URL** | `SUPABASE_URL` | `https://xxx.supabase.co` |
| **anon/public key** | Not needed for backend | |
| **service_role key** | `SUPABASE_KEY` | `ey...` |

3. Go to **Settings** → **API** → Scroll to **JWT Settings**
4. Copy **JWT Secret** → This is `SUPABASE_JWT_SECRET`

⚠️ **Security Note**: The `service_role` key bypasses Row Level Security. Keep it secret!

### Step 1.4: Create Storage Buckets

1. In Supabase dashboard, click **Storage** in the sidebar
2. Click **"New bucket"**

**Bucket 1: Private Documents**
- **Name**: `notebook-private`
- **Public bucket**: ❌ **Unchecked** (Private)
- **Allowed MIME types**: Leave empty (allow all)
- Click **"Create bucket"**

**Bucket 2: Public Content**
- **Name**: `notebook-public`
- **Public bucket**: ✅ **Checked** (Public)
- **Allowed MIME types**: Leave empty (allow all)
- Click **"Create bucket"**

### Step 1.5: Enable Authentication (Optional)

1. Go to **Authentication** → **Providers**
2. Ensure **Email** is enabled (it's enabled by default)
3. For production, configure:
   - **Site URL**: Your frontend URL
   - **Redirect URLs**: Add your allowed redirect URLs

---

## 2. Qdrant Setup

Qdrant is the vector database for semantic search. Choose one option:

### Option A: Docker (Local Development - Recommended)

**Easiest for local development and testing.**

```bash
# Start Qdrant container
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# Verify it's running
curl http://localhost:6333
```

**Configure in `.env`:**
```env
QDRANT_HOST=http://localhost:6333
QDRANT_API_KEY=  # Leave empty for local Docker
```

### Option B: Qdrant Cloud (Production / Easier Setup)

**Best for production or if you don't want to manage Docker.**

1. Go to [cloud.qdrant.io](https://cloud.qdrant.io/)
2. Sign up and create a new cluster
3. Choose **Free Tier** (1GB storage, sufficient for testing)
4. Copy:
   - **Cluster URL** (e.g., `https://xxx.aws.cloud.qdrant.io:6333`)
   - **API Key**

**Configure in `.env`:**
```env
QDRANT_HOST=https://xxx.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your_api_key_here
```

### Option C: Self-Hosted (Advanced)

See [Qdrant documentation](https://qdrant.tech/documentation/guides/installation/) for installation on your own server.

---

## 3. Backend Installation

### Step 3.1: Clone the Repository

```bash
# Clone the repo
git clone <your-repo-url>
cd granthiq/backend
```

### Step 3.2: Create Virtual Environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Verify activation:**
```bash
which python  # macOS/Linux
where python  # Windows
# Should point to .venv/bin/python or .venv\Scripts\python
```

### Step 3.3: Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

**This will install:**
- FastAPI, Uvicorn (web framework)
- SQLModel, Alembic (database ORM and migrations)
- LlamaIndex (RAG framework)
- Qdrant client (vector database)
- Supabase client (storage and auth)
- Many more...

**Estimated time:** 3-5 minutes

---

## 4. Environment Configuration

### Step 4.1: Create `.env` File

```bash
# Copy the example file
cp .env.example .env

# Edit with your favorite editor
nano .env  # or code .env or vim .env
```

### Step 4.2: Configure Required Variables

Edit `.env` and fill in the following **required** variables:

#### Database & Supabase

```env
# PostgreSQL Database (from Step 1.2)
DATABASE_URL=postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.xxx.supabase.co:5432/postgres?ssl=require

# Supabase API URL (from Step 1.3)
SUPABASE_URL=https://xxx.supabase.co

# Supabase Service Role Key (from Step 1.3)
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# JWT Secret (from Step 1.3)
SUPABASE_JWT_SECRET=your-jwt-secret-from-supabase
```

#### Vector Database

```env
# Qdrant (from Step 2)
QDRANT_HOST=http://localhost:6333  # or your Qdrant Cloud URL
QDRANT_API_KEY=  # Leave empty for local Docker, or add your API key
QDRANT_COLLECTION_NAME=granthiq
```

#### LLM Provider (at least one required)

```env
# Google Gemini (Recommended - Free tier available)
GEMINI_API_KEY=AIzaSy...  # Get from aistudio.google.com

# OR Groq (Very fast, free tier)
GROQ_API_KEY=gsk_...  # Get from console.groq.com

# OR OpenAI (Paid, but high quality)
OPENAI_API_KEY=sk-...  # Get from platform.openai.com
```

#### API Configuration

```env
# CORS Origins (comma-separated)
# Add your frontend URL here
API__CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Rate Limiting
ENABLE_RATE_LIMITING=true

# Environment
ENVIRONMENT=development
DEBUG=true
```

### Step 4.3: Configure Optional Variables (Recommended)

#### Reranking (Improves search quality significantly)

```env
# Cohere API (Free tier: 1000 calls/month)
COHERE_API_KEY=your_cohere_key  # Get from dashboard.cohere.com
```

#### Observability (LLM tracing and monitoring)

```env
# Langfuse (Free tier available)
LANGFUSE_PUBLIC_KEY=pk-lf-...  # Get from cloud.langfuse.com
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_ENABLED=true
```

#### Additional Services (Optional)

```env
# Firecrawl - Web scraping (if you want to import from URLs)
FIRECRAWL_API_KEY=fc-...  # Get from firecrawl.dev

# AssemblyAI - Audio transcription (if you want to process audio files)
ASSEMBLYAI_API_KEY=...  # Get from assemblyai.com
```

### Step 4.4: Verify Configuration

```bash
# Quick check: Make sure all required vars are set
python -c "from src.config import get_settings; print('✅ Configuration loaded successfully!')"
```

**See [.env.example](.env.example) for complete list of all configuration options.**

---

## 5. Database Initialization

⚠️ **IMPORTANT**: Database setup requires **two steps** due to Procrastinate's use of PostgreSQL-specific features.

### Step 5.1: Apply Procrastinate Schema

Procrastinate is our background task queue. It uses PostgreSQL triggers and stored procedures.

```bash
# Apply Procrastinate database schema
python -m procrastinate --app src.services.queue.app.proc_app schema --apply
```

**Expected output:**
```
Procrastinate schema applied
```

**What this does:**
- Creates `procrastinate_jobs` table
- Creates `procrastinate_events` table
- Sets up triggers and functions for job processing
- Configures LISTEN/NOTIFY for real-time updates

### Step 5.2: Apply Application Migrations

Now apply our application's database schema (notebooks, documents, messages, etc.)

```bash
# Run Alembic migrations
alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime.migration] Running upgrade -> abc123, create users table
INFO  [alembic.runtime.migration] Running upgrade abc123 -> def456, create notebooks
INFO  [alembic.runtime.migration] Running upgrade def456 -> ghi789, create documents
...
INFO  [alembic.runtime.migration] Running upgrade xyz -> head
```

**What this does:**
- Creates user tables (`users`)
- Creates notebook tables (`notebooks`, `documents`)
- Creates chat tables (`chat_messages`, `message_citations`)
- Creates content tables (`generated_content`)
- Creates task tracking tables (`task_progress`)

### Step 5.3: Verify Database Setup

```bash
# Check if tables were created (optional)
python -c "
from src.db.session import engine
import asyncio
async def check():
    async with engine.begin() as conn:
        result = await conn.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=\\'public\\'')
        tables = [row[0] for row in result]
        print(f'✅ Created {len(tables)} tables: {tables}')
asyncio.run(check())
"
```

---

## 6. Running the Application

### Step 6.1: Start the Development Server

```bash
# Make sure virtual environment is activated
# You should see (.venv) in your terminal prompt

# Start FastAPI server with hot reload
uvicorn src.app:app --reload
```

**Expected output:**
```
INFO:     Will watch for changes in these directories: ['/path/to/backend']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Alternative:** You can also run:
```bash
python -m src.app
```

### Step 6.2: Server Access Points

Once running, you can access:

| URL | Description |
|-----|-------------|
| http://localhost:8000 | Root endpoint (redirects to /docs) |
| http://localhost:8000/docs | **Swagger UI** - Interactive API docs |
| http://localhost:8000/redoc | **ReDoc** - Alternative API documentation |
| http://localhost:8000/api/v1/health | Health check endpoint |
| http://localhost:8000/openapi.json | OpenAPI schema |

### Step 6.3: Background Worker (Optional)

For production or testing background tasks:

**Embedded Mode (Recommended for development):**
```bash
# Worker runs alongside API
export ENABLE_EMBEDDED_WORKER=true  # macOS/Linux
set ENABLE_EMBEDDED_WORKER=true     # Windows

uvicorn src.app:app --reload
```

**Standalone Mode:**
```bash
# Run worker separately (in a new terminal)
python -m src.services.queue.worker
```

---

## 7. Verification

### Test 1: Health Check

```bash
# Test health endpoint (no auth required)
curl http://localhost:8000/api/v1/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-17T01:30:00Z",
  "services": {
    "database": {"status": "healthy"},
    "vector_database": {"status": "healthy"},
    "storage": {"status": "healthy"},
    "llm_provider": {"status": "healthy", "provider": "gemini"}
  }
}
```

### Test 2: Interactive API Docs

1. Open http://localhost:8000/docs in your browser
2. You should see the Swagger UI interface
3. Click on any endpoint to see details
4. Try the `/api/v1/health` endpoint:
   - Click **"Try it out"**
   - Click **"Execute"**
   - Check the response

### Test 3: Create a Test Notebook (Requires Frontend)

If you have the frontend running:

1. Sign up at http://localhost:3000
2. Create a new notebook
3. Upload a test document (PDF or TXT)
4. Check the logs in your backend terminal - you should see processing messages

---

## 8. Troubleshooting

### Common Issues

#### Issue 1: `ModuleNotFoundError: No module named 'src'`

**Solution:**
```bash
# Make sure you're in the backend directory
cd backend

# Ensure virtual environment is activated
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

#### Issue 2: Database Connection Error

**Error:** `asyncpg.exceptions.InvalidPasswordError` or `could not connect to server`

**Solution:**
1. Check `DATABASE_URL` in `.env`
2. Verify password is correct (no special characters need escaping in URI format)
3. Ensure `ssl=require` is at the end
4. Check if your IP is allowed in Supabase (Dashboard → Settings → Database → Connection Pooling)

#### Issue 3: Qdrant Connection Error

**Error:** `QdrantException: Could not connect to Qdrant`

**Solution:**
```bash
# If using Docker, check if container is running
docker ps | grep qdrant

# If not running, start it
docker run -d -p 6333:6333 --name qdrant qdrant/qdrant

# Test connection
curl http://localhost:6333
```

#### Issue 4: Procrastinate Schema Error

**Error:** `sqlalchemy.exc.ProgrammingError: relation "procrastinate_jobs" does not exist`

**Solution:**
```bash
# Apply Procrastinate schema first
python -m procrastinate --app src.services.queue.app.proc_app schema --apply

# Then run Alembic migrations
alembic upgrade head
```

#### Issue 5: Supabase Storage 404 Error

**Error:** `StorageException: Bucket not found`

**Solution:**
1. Go to Supabase Dashboard → Storage
2. Create buckets manually:
   - `notebook-private` (private)
   - `notebook-public` (public)
3. Restart backend server

#### Issue 6: LLM API Key Error

**Error:** `google.api_core.exceptions.PermissionDenied: API key not valid`

**Solution:**
1. Get a new API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Update `GEMINI_API_KEY` in `.env`
3. Restart server

#### Issue 7: Port Already in Use

**Error:** `OSError: [Errno 48] Address already in use`

**Solution:**
```bash
# Find process using port 8000
# macOS/Linux:
lsof -i :8000
kill -9 <PID>

# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Or use a different port:
uvicorn src.app:app --reload --port 8001
```

---

## 9. Next Steps

✅ **You're all set!** Your backend is now running. Here's what to do next:

### 1. Set Up Frontend

```bash
cd ../granthiq
npm install
cp .env.example .env.local
# Edit .env.local with your Supabase credentials
npm run dev
```

### 2. Explore API Documentation

- Open http://localhost:8000/docs
- Try out different endpoints
- Use the "Authorize" button to test authenticated endpoints

### 3. Test Document Upload

1. Run frontend
2. Sign up / Sign in
3. Create a notebook
4. Upload a PDF or text file
5. Check backend logs for processing status

### 4. Enable Observability (Optional)

1. Sign up for [Langfuse](https://cloud.langfuse.com/)
2. Get API keys
3. Add to `.env`:
   ```env
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_ENABLED=true
   ```
4. Restart server
5. Check traces at https://cloud.langfuse.com/

### 5. Read Documentation

- [API Reference](API.md) - Complete endpoint documentation
- [Architecture Guide](ARCHITECTURE.md) - System design
- [Deployment Guide](DEPLOYMENT.md) - Production deployment
- [Technical Challenges](TECHNICAL_CHALLENGES_AND_SOLUTIONS.md) - Engineering insights

---

## 📚 Additional Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Supabase Docs**: https://supabase.com/docs
- **Qdrant Docs**: https://qdrant.tech/documentation/
- **LlamaIndex Docs**: https://docs.llamaindex.ai/

---

## 💬 Support

If you encounter issues:

1. Check the [Troubleshooting](#8-troubleshooting) section above
2. Search existing [GitHub Issues](https://github.com/yourusername/granthiq/issues)
3. Create a new issue with:
   - Error message
   - Steps to reproduce
   - Environment details (OS, Python version, etc.)

---

**Setup Complete!** 🎉 You now have a fully functional Granthiq backend running locally.
