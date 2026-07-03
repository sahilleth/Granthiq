# Granthiq - RAG-Powered Document Intelligence Platform

A production-ready RAG application for chatting with notebooks and documents, built with FastAPI, LangChain, and Qdrant.

## 🏗️ Technology Stack

### Core Framework
| Package | Purpose | Why Essential |
|---------|---------|---------------|
| `fastapi` | Backend API framework | Modern, fast, automatic API documentation |
| `uvicorn` | ASGI server | Production-ready async server for FastAPI |
| `pydantic` | Data validation | Type-safe request/response validation |
| `pydantic-settings` | Configuration management | Environment-based settings with validation |
| `python-dotenv` | Environment variables | Secure API key management |

### RAG & AI
| Package | Purpose | Why Essential |
|---------|---------|---------------|
| `langchain` | Agent orchestration & chains | RAG pipeline orchestration |
| `langchain-google-genai` | Gemini integration | Google's Gemini LLM support |
| `llama-index` | Document indexing & retrieval | Fast, optimized retrieval engine |
| `qdrant-client` | Vector database | Self-hostable, production-ready vector DB |
| `sentence-transformers` | Embeddings | Free, local semantic embeddings |
| `groq` | Fast LLM inference | Ultra-fast LLM API |
| `google-generativeai` | Gemini API | Google's powerful LLM |

### Document Processing
| Package | Purpose | Why Essential |
|---------|---------|---------------|
| `pypdf` | PDF parsing | Extract text from PDF documents |
| `beautifulsoup4` | HTML parsing | Web document processing |
| `unstructured` | Multi-format parsing | Advanced document processing |
| `nbformat` | Jupyter notebook support | Notebook-specific processing |

### Utilities
| Package | Purpose | Why Essential |
|---------|---------|---------------|
| `httpx` | Async HTTP requests | High-performance HTTP client |
| `requests` | HTTP requests | Synchronous HTTP operations |
| `tiktoken` | Token counting | Accurate token usage tracking |
| `tenacity` | Retry logic | Robust API call handling |
| `loguru` | Logging | Better logging experience |

### Testing
| Package | Purpose | Why Essential |
|---------|---------|---------------|
| `pytest` | Testing framework | Professional testing |
| `pytest-asyncio` | Async testing | Test async endpoints |

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.12+
- Qdrant running (Docker or local)

### 2. Installation

```bash
# Clone the repository
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file in the `backend` directory:

```bash
cp .env.example .env
```

Edit `.env` with your API keys:
```env
# LLM Configuration
LLM__PROVIDER=groq  # or "gemini"
LLM__MODEL_NAME=llama-3.3-70b-versatile
LLM__GROQ_API_KEY=your_groq_api_key
LLM__GEMINI_API_KEY=your_gemini_api_key

# Vector Database
QDRANT__HOST=http://localhost:6333
QDRANT__COLLECTION_NAME=notebook_documents

# Application
API__HOST=0.0.0.0
API__PORT=8000
DEBUG=true
```

### 4. Start Qdrant

Using Docker:
```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 5. Run the Application

```bash
# Development
python -m uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000/docs` for interactive API documentation.

## 📁 Project Structure

```
backend/
├── src/
│   ├── api/              # API routers
│   │   └── routers/      # Route handlers
│   ├── services/         # Business logic
│   ├── config/           # Configuration
│   ├── models/           # Pydantic models
│   └── prompts/          # Prompt templates
├── main.py               # FastAPI application
├── requirements.txt      # Dependencies
└── .env.example          # Environment template
```

## 🔑 Key Features

- ✅ **Multi-LLM Support**: Switch between Gemini and Groq
- ✅ **Hybrid RAG Architecture**: LlamaIndex for indexing + LangChain for orchestration
- ✅ **Notebook Processing**: Jupyter notebook-aware chunking
- ✅ **Vector Search**: Semantic search with Qdrant
- ✅ **Document Support**: PDF, notebooks, text files
- ✅ **Production Ready**: Logging, error handling, async

## 📚 API Endpoints

- `GET /health` - Health check
- `POST /api/v1/chat` - Chat with documents
- `POST /api/v1/documents/upload` - Upload documents
- `GET /api/v1/documents` - List documents

## 🔧 Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest

# Format code
black src/

# Type checking
mypy src/
```

## 📝 Environment Variables

See `.env.example` for all available configuration options. Key variables:

- `LLM__PROVIDER`: LLM provider (groq/gemini)
- `LLM__GROQ_API_KEY`: Groq API key
- `LLM__GEMINI_API_KEY`: Gemini API key
- `QDRANT__HOST`: Qdrant server URL
- `API__PORT`: Server port

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📄 License

MIT License
