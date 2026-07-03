#!/usr/bin/env python3
"""
Granthiq MCP Server — expose notebook search and Q&A to Cursor, Claude Desktop, etc.

Usage:
  export GRANTHIQ_API_URL=http://localhost:8000
  export GRANTHIQ_API_TOKEN=<supabase_jwt>
  python server.py
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

GRANTHIQ_API_URL = os.environ.get("GRANTHIQ_API_URL", "http://localhost:8000").rstrip("/")
GRANTHIQ_API_TOKEN = os.environ.get("GRANTHIQ_API_TOKEN", "")

mcp = FastMCP(
    "Granthiq",
    instructions=(
        "Granthiq document intelligence platform. Search and query user notebooks "
        "with hybrid RAG (semantic + BM25), citations, and optional research agent mode."
    ),
)


def _headers() -> dict[str, str]:
    if not GRANTHIQ_API_TOKEN:
        raise ValueError(
            "GRANTHIQ_API_TOKEN is required. Sign in to Granthiq and pass your Supabase JWT."
        )
    return {
        "Authorization": f"Bearer {GRANTHIQ_API_TOKEN}",
        "Content-Type": "application/json",
    }


async def _api(method: str, path: str, **kwargs: Any) -> Any:
    async with httpx.AsyncClient(base_url=f"{GRANTHIQ_API_URL}/api/v1", timeout=120.0) as client:
        response = await client.request(method, path, headers=_headers(), **kwargs)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()


@mcp.tool()
async def list_notebooks(limit: int = 20) -> str:
    """List the authenticated user's notebooks with source counts."""
    data = await _api("GET", "/notebooks", params={"limit": limit})
    items = data.get("items", data if isinstance(data, list) else [])
    summary = [
        {
            "id": n.get("id"),
            "title": n.get("title"),
            "source_count": n.get("source_count", 0),
            "updated_at": n.get("updated_at"),
        }
        for n in items
    ]
    return json.dumps(summary, indent=2)


@mcp.tool()
async def list_documents(notebook_id: str, limit: int = 50) -> str:
    """List documents in a notebook with processing status."""
    data = await _api("GET", f"/documents/notebook/{notebook_id}", params={"limit": limit})
    items = data.get("items", [])
    summary = [
        {
            "id": d.get("id"),
            "filename": d.get("filename"),
            "status": d.get("status"),
            "chunk_count": d.get("chunk_count"),
        }
        for d in items
    ]
    return json.dumps(summary, indent=2)


@mcp.tool()
async def ask_notebook(
    notebook_id: str,
    question: str,
    mode: str = "chat",
) -> str:
    """
    Ask a question against a notebook using Granthiq RAG.

    Args:
        notebook_id: UUID of the notebook
        question: User question
        mode: 'chat' for fast single-shot RAG, 'research' for multi-step research agent
    """
    if mode not in ("chat", "research"):
        mode = "chat"

    data = await _api(
        "POST",
        f"/chat/{notebook_id}/message",
        json={"message": question, "stream": False, "mode": mode},
    )

    result = {
        "answer": data.get("message") or data.get("content", ""),
        "confidence": data.get("confidence"),
        "citations": [
            {
                "index": i + 1,
                "filename": c.get("filename"),
                "score": c.get("score"),
                "preview": c.get("text_preview", "")[:200],
                "page": c.get("page_number"),
            }
            for i, c in enumerate(data.get("citations", []))
        ],
    }
    return json.dumps(result, indent=2)


@mcp.tool()
async def research_notebook(notebook_id: str, question: str) -> str:
    """Run the multi-step research agent on a notebook (plan → search → synthesize)."""
    return await ask_notebook(notebook_id, question, mode="research")


@mcp.tool()
async def get_chat_history(notebook_id: str, limit: int = 10) -> str:
    """Get recent chat history for a notebook."""
    data = await _api("GET", f"/chat/{notebook_id}/history", params={"limit": limit})
    items = data.get("items", [])
    return json.dumps(items, indent=2)


if __name__ == "__main__":
    mcp.run()
