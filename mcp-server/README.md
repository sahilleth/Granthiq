# Granthiq MCP Server

Expose your Granthiq notebooks to **Cursor**, **Claude Desktop**, and any MCP-compatible client.

## Tools

| Tool | Description |
|------|-------------|
| `list_notebooks` | List your notebooks |
| `list_documents` | List documents in a notebook |
| `ask_notebook` | RAG Q&A (`mode`: `chat` or `research`) |
| `research_notebook` | Multi-step research agent |
| `get_chat_history` | Recent chat messages |

## Setup

### 1. Get an API token

Sign in to Granthiq and copy your Supabase JWT (browser devtools → Application → local storage, or use the backend `scripts/generate_token.py` in dev).

### 2. Install dependencies

```bash
cd mcp-server
pip install -r requirements.txt
```

### 3. Configure environment

```bash
export GRANTHIQ_API_URL=http://localhost:8000
export GRANTHIQ_API_TOKEN=eyJhbGciOi...
```

### 4. Cursor / Claude Desktop config

Add to your MCP settings (`~/.cursor/mcp.json` or Claude Desktop config):

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

## Example prompts (in Cursor)

- "List my Granthiq notebooks"
- "Ask my ML notebook: what optimization techniques are discussed?"
- "Run research mode on notebook `<id>`: compare the three papers on retrieval quality"

## Architecture

```
Cursor / Claude Desktop
        │ MCP (stdio)
        ▼
   mcp-server/server.py
        │ REST + JWT
        ▼
   Granthiq FastAPI Backend
        │ hybrid RAG / research agent
        ▼
   Qdrant + PostgreSQL
```
