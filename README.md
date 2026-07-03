# Granthiq

**Knowledge, witnessed.**

Granthiq is an AI-powered document intelligence platform — upload sources, ask hard questions, get answers that cite every claim.

## Stack

- **Frontend:** Next.js 16, React 19, Tailwind CSS, Supabase Auth
- **Backend:** FastAPI, LlamaIndex, Procrastinate
- **Data:** Supabase (Postgres + Storage), Qdrant (vectors)

## Quick Start

See [LOCAL_SETUP.md](./LOCAL_SETUP.md) for full setup instructions (~30–45 min).

```bash
# Backend
cd backend && uv sync && cp .env.example .env
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm install && cp .env.example .env.local
npm run dev
```

Open http://localhost:3000

## Documentation

| Doc | Description |
|-----|-------------|
| [LOCAL_SETUP.md](./LOCAL_SETUP.md) | Step-by-step local dev guide |
| [InterviewNotes.md](./InterviewNotes.md) | End-to-end project walkthrough for interviews |
| [DEBUGGING_NOTES.md](./DEBUGGING_NOTES.md) | Real bugs, diagnoses, and fixes |
| [docs/PORTFOLIO_FEATURES.md](./docs/PORTFOLIO_FEATURES.md) | Confidence UI, Research Agent, MCP |
| [backend/docs/](./backend/docs/) | Backend architecture, API, deployment |
| [mcp-server/README.md](./mcp-server/README.md) | MCP integration for Cursor / Claude Desktop |

## Project Structure

```
Granthiq/
├── frontend/     # Next.js app
├── backend/      # FastAPI + RAG pipeline
├── mcp-server/   # MCP tool provider
└── docs/         # Portfolio & feature docs
```

## License

See repository for license details.
