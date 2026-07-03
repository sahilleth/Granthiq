# Granthiq — Local Setup Guide

Step-by-step instructions to run **Granthiq** on your machine.

**Time:** ~30–45 minutes (first time)  
**Stack:** Next.js frontend · FastAPI backend · Supabase (Postgres + Auth + Storage) · Qdrant (vectors)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone the repo](#2-clone-the-repo)
3. [Supabase (one-time)](#3-supabase-one-time)
4. [Qdrant (vector database)](#4-qdrant-vector-database)
5. [Backend setup](#5-backend-setup)
6. [Database migrations](#6-database-migrations)
7. [Run the backend](#7-run-the-backend)
8. [Frontend setup](#8-frontend-setup)
9. [Run the frontend](#9-run-the-frontend)
10. [Verify everything works](#10-verify-everything-works)
11. [Optional: MCP server](#11-optional-mcp-server)
12. [Daily dev workflow](#12-daily-dev-workflow)
13. [Common issues](#13-common-issues)

---

## 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
| **Python** | 3.12+ | [python.org](https://www.python.org/downloads/) |
| **uv** (Python package manager) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Git** | latest | [git-scm.com](https://git-scm.com/) |
| **Docker** (optional, for local Qdrant) | latest | [docker.com](https://www.docker.com/) |

**macOS (Apple Silicon) — file type detection for PDF uploads:**

```bash
brew install libmagic
```

**Accounts / API keys you'll need:**

| Service | Required? | Get key |
|---------|-----------|---------|
| [Supabase](https://supabase.com) | **Yes** | Free tier — DB, auth, storage |
| [Google AI Studio](https://aistudio.google.com/) | **Yes** | Gemini API key (chat + TTS) |
| [Groq](https://console.groq.com/) | Recommended | Fast LLM + HyDE query expansion |
| [Qdrant Cloud](https://cloud.qdrant.io/) or Docker | **Yes** | Vector search |
| [Cohere](https://dashboard.cohere.com/) | Optional | Reranking (better citations) |

---

## 2. Clone the repo

```bash
git clone <your-repo-url>
cd granthiq   # or whatever you named the folder
```

---

## 3. Supabase (one-time)

### 3.1 Create a project

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard) → **New project**
2. Save your **database password**

### 3.2 Get credentials

From **Settings → API**:

| Variable | Where to find it |
|----------|------------------|
| Project URL | → `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL` |
| `anon` / publishable key | → frontend env |
| `service_role` key | → backend `SUPABASE_KEY` (keep secret) |
| JWT Secret | **Settings → API → JWT Settings** → `SUPABASE_JWT_SECRET` |

From **Settings → Database → Connection string (URI)**:

```
postgresql+asyncpg://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres?sslmode=require
```

→ backend `DATABASE_URL`  
(URL-encode special characters in the password, e.g. `#` → `%23`)

### 3.3 Create storage buckets

**Storage → New bucket:**

| Name | Public? | File size limit |
|------|---------|-----------------|
| `notebook-private` | No (private) | 50 MB |
| `notebook-public` | Yes | 50 MB |

### 3.4 Enable Google OAuth (optional)

1. **Authentication → Providers → Google** → enable
2. Add redirect URL: `http://localhost:3000/auth/callback`
3. Set Google OAuth client ID + secret from [Google Cloud Console](https://console.cloud.google.com/)

### 3.5 Run SQL scripts (Supabase SQL Editor)

Run these once in **SQL Editor → New query**:

**A. Enable Row Level Security**

```bash
# Copy contents of this file into Supabase SQL Editor and run:
cat backend/migrations/enable_rls.sql
```

**B. Sync auth users → app `public.user` table**

```bash
cat backend/migrations/supabase_user_sync_trigger.sql
```

Without (B), Google sign-up creates a user in `auth.users` but **not** in `public.user`, and notebook creation will fail.

---

## 4. Qdrant (vector database)

### Option A — Qdrant Cloud (recommended)

1. Create a free cluster at [cloud.qdrant.io](https://cloud.qdrant.io/)
2. Copy **Cluster URL** and **API key**

### Option B — Local Docker

```bash
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

Use `QDRANT_HOST=http://localhost:6333` and leave `QDRANT_API_KEY` empty.

---

## 5. Backend setup

### 5.1 Install dependencies

```bash
cd backend
uv sync
```

> On Apple Silicon, `uv sync` picks the correct `python-magic` package automatically.

### 5.2 Create environment file

```bash
cp .env.example .env
```

Edit `backend/.env`. **Minimum required values:**

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres?sslmode=require

# Supabase
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=your-service-role-key          # NOT the anon key
SUPABASE_JWT_SECRET=your-jwt-secret

# Storage — base URL only, NO /storage/v1 suffix
STORAGE_URL=https://YOUR_PROJECT.supabase.co
STORAGE_PROVIDER=supabase
STORAGE_PUBLIC_BUCKET=notebook-public
STORAGE_PRIVATE_BUCKET=notebook-private

# Qdrant
QDRANT_HOST=https://your-cluster.qdrant.io   # or http://localhost:6333
QDRANT_API_KEY=your-qdrant-api-key           # empty for local Docker
QDRANT_COLLECTION_NAME=Notebookllm           # must match existing collection if reusing data
QDRANT_USE_HTTPS=true                        # false for local Docker

# LLM
LLM__PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
LLM__MODEL_NAME=gemini-2.5-flash             # use LLM__MODEL_NAME, not LLM__GEMINI_MODEL

# Groq (recommended — used for HyDE + fast generation)
GROQ_API_KEY=your-groq-api-key

# Cohere (optional — reranking; skip or use real key, not placeholder)
COHERE_API_KEY=your_cohere_api_key_here

# CORS
API__CORS_ORIGINS=["http://localhost:3000"]

# Observability (disable if you don't have keys)
LANGFUSE_ENABLED=false

# Background worker (runs inside API process by default)
ENABLE_EMBEDDED_WORKER=true
```

**Critical env pitfalls (we hit these during setup):**

| Mistake | Fix |
|---------|-----|
| `STORAGE_URL` includes `/storage/v1` | Use base URL only: `https://xxx.supabase.co` |
| `SUPABASE_KEY` is the anon key | Use **service_role** key for storage writes |
| `LLM__GEMINI_MODEL` in `.env` | Wrong var name — use `LLM__MODEL_NAME` |
| Placeholder `COHERE_API_KEY=your_cohere...` | Use a real key or leave empty |
| `.env` changes not picked up | Restart backend (`uvicorn` does not hot-reload `.env`) |

### 5.3 Verify config loads

```bash
cd backend
uv run python -c "from src.config import get_settings; s = get_settings(); print('OK:', s.app_name)"
```

---

## 6. Database migrations

Run from the `backend/` directory:

### 6.1 Procrastinate task queue schema

```bash
uv run python -m procrastinate --app src.services.queue.app.proc_app schema --apply
```

### 6.2 Alembic application migrations

```bash
uv run alembic upgrade head
```

Expected: migrations apply without error (including `confidence` column on chat messages).

---

## 7. Run the backend

```bash
cd backend
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

**Endpoints:**

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | Swagger API docs |
| http://localhost:8000/api/v1/health | Health check |

The embedded worker starts automatically (`ENABLE_EMBEDDED_WORKER=true`) and processes document uploads in the background.

**Separate worker (optional):**

```bash
# Terminal 2 — only if ENABLE_EMBEDDED_WORKER=false
cd backend
uv run python -m src.services.queue.worker
```

---

## 8. Frontend setup

### 8.1 Install dependencies

```bash
cd frontend
npm install
```

### 8.2 Create environment file

```bash
cp .env.example .env.local
```

Edit `frontend/.env.local`:

```env
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-anon-or-publishable-key
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

> Both `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are used — set both to your Supabase **anon** key.

---

## 9. Run the frontend

```bash
cd frontend
npm run dev
```

Open **http://localhost:3000**

If port 3000 is busy, Next.js will use 3001 — check the terminal output.

**Kill stale dev servers if you see old UI:**

```bash
pkill -f "next dev"
rm -rf frontend/.next
cd frontend && npm run dev
```

---

## 10. Verify everything works

### Health check

```bash
curl http://localhost:8000/api/v1/health
```

All services should report `"status": "healthy"`.

### Manual smoke test

1. Open http://localhost:3000
2. **Sign up** (email or Google OAuth)
3. **Create a notebook**
4. **Upload a PDF** — wait for status `completed`
5. **Ask a question** in chat — response should stream with citations
6. Toggle **Research Agent** — agent steps (plan → search → synthesize) should appear
7. **Reload the page** — confidence badge should persist on assistant messages

---

## 11. Optional: MCP server

Exposes notebooks to Cursor / Claude Desktop.

```bash
cd mcp-server
pip install -r requirements.txt
```

Get a JWT (sign in to the app, or use the dev script):

```bash
cd backend
uv run python scripts/generate_token.py
```

Run / register in Cursor (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "granthiq": {
      "command": "python",
      "args": ["/absolute/path/to/granthiq/mcp-server/server.py"],
      "env": {
        "GRANTHIQ_API_URL": "http://localhost:8000",
        "GRANTHIQ_API_TOKEN": "your-jwt-here"
      }
    }
  }
}
```

See [mcp-server/README.md](mcp-server/README.md) for full details.

---

## 12. Daily dev workflow

Open **two terminals**:

```bash
# Terminal 1 — Backend
cd backend
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Then open http://localhost:3000

---

## 13. Common issues

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Failed to fetch` on API calls | Backend not running or still reloading | Wait for `Application startup complete`, retry |
| Google login → blank screen | OAuth cookie handling | See `DEBUGGING_NOTES.md` §5 |
| Upload fails: `Route not found` | Missing buckets or wrong `STORAGE_URL` | Create buckets; fix `STORAGE_URL` (no `/storage/v1`) |
| Chat hangs, no response | Groq rate limit or bad Cohere key | Cap HyDE tokens; fix/remove placeholder Cohere key |
| `408 Request timeout` on polling | DB connection leak (fixed) | Restart backend |
| Notebook create fails after OAuth | No `public.user` row | Run `supabase_user_sync_trigger.sql` |
| Citations show **0%** | RRF fusion scores not normalized | Known issue — fix pending |
| Old pricing/testimonials still visible | Stale Next.js cache | `pkill -f "next dev" && rm -rf frontend/.next` |

Full troubleshooting journal: **[DEBUGGING_NOTES.md](DEBUGGING_NOTES.md)**

---

## Project structure (quick reference)

```
granthiq/
├── backend/          # FastAPI API + RAG pipeline + worker
│   ├── .env          # Backend secrets (create from .env.example)
│   ├── src/app.py    # App entry point
│   └── migrations/   # Alembic + SQL scripts (RLS, user sync)
├── frontend/         # Next.js 14 app
│   ├── .env.local    # Frontend public env vars
│   └── app/          # Pages (landing, notebook, docs, auth)
├── mcp-server/       # MCP tools for Cursor / Claude Desktop
├── docs/             # Portfolio features doc
├── DEBUGGING_NOTES.md
└── LOCAL_SETUP.md    # ← this file
```
