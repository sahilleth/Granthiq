# Granthiq Backend

<div align="center">
  <img src="docs/white-logo.svg" alt="Granthiq Logo" width="200">

**FastAPI Backend for AI-Powered Document Intelligence**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009FDA?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

FastAPI application with Supabase, LangChain, and AI integrations for the Granthiq AI research assistant.

[Frontend Repo](https://github.com/MohitGoyal09/Granthiq) • [Features](#features) • [Tech Stack](#tech-stack) • [Quick Start](#quick-start) • [Deployment](#deployment)

</div>

---

## 🎯 Overview

The Granthiq backend provides a powerful API for document processing, AI-powered chat, and content generation. It leverages modern AI frameworks to transform documents into interactive knowledge bases.

Built for production with async processing, streaming responses, and enterprise-grade security.

---

## 🏛️ Architecture

<p align="center">
  <img src="docs/architecture.png" alt="Granthiq Architecture" width="900">
</p>

The backend follows a **service-oriented architecture** with a focus on asynchronous processing and reliable document ingestion.

---

## ✨ Features

- **Document Processing**: PDF, TXT, DOCX, audio, YouTube, and web content extraction
- **AI Chat**: Contextual Q&A with source citations and streaming responses
- **Content Generation**: Create podcasts, quizzes, flashcards, mindmaps, and more
- **Vector Search**: Semantic search using Pinecone embeddings
- **Authentication**: Supabase Auth with JWT tokens
- **Real-time**: Server-Sent Events (SSE) for streaming responses

---

## 🛠️ Tech Stack

| Category | Technology |
|----------|------------|
| Framework | FastAPI |
| Language | Python 3.11+ |
| Database | PostgreSQL + Supabase |
| ORM | SQLAlchemy + Alembic |
| AI | LangChain, OpenAI, Anthropic, Google Gemini |
| Embeddings | OpenAI, Google |
| Vector DB | Pinecone |
| TTS | Google Cloud TTS, ElevenLabs |
| YouTube | yt-dlp |
| Deployment | Docker, Coolify |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL database (local or Supabase)
- API keys for AI providers

### Installation

```bash
cd backend
uv sync
```

### Environment Setup

Copy `.env.example` to `.env` and configure:

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/granthiq

# AI Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Pinecone
PINECONE_API_KEY=...
PINECONE_INDEX=granthiq
```

### Development

```bash
uv run uvicorn src.main:app --reload
```

API docs available at [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 📁 Project Structure

```
backend/
├── src/
│   ├── api/              # API routes
│   │   └── v1/
│   │       ├── notebooks.py
│   │       ├── chat.py
│   │       ├── sources.py
│   │       └── ...
│   ├── core/             # Core config
│   │   ├── config.py
│   │   ├── security.py
│   │   └── supabase.py
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic
│   │   ├── ai/
│   │   ├── chat/
│   │   ├── documents/
│   │   └── storage/
│   └── main.py           # App entry point
├── migrations/            # Alembic migrations
├── tests/                # Test files
└── alembic.ini           # Alembic config
```

---

## 🐳 Docker

```bash
docker-compose up -d
```

---

## 🚢 Deployment

### Coolify

See [docs/COOLIFY_DEPLOYMENT.md](docs/COOLIFY_DEPLOYMENT.md) for detailed deployment instructions.

### Docker Compose

```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📡 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/notebooks` | Create notebook |
| `GET /api/v1/notebooks/{id}` | Get notebook |
| `POST /api/v1/sources/upload` | Upload document |
| `POST /api/v1/chat/message` | Send chat message |
| `GET /api/v1/studio/{type}` | Generate content |

See [http://localhost:8000/docs](http://localhost:8000/docs) for full API documentation.

---

## 🤝 Contributing

1. Follow the existing code style (ruff)
2. Write tests for new features
3. Update documentation

---

## 📜 License

MIT License
