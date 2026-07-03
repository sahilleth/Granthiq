"""
Mock services for isolated testing.
Provides fake implementations of external dependencies.
"""

from unittest.mock import AsyncMock, MagicMock
from typing import Optional, Dict, Any, List, AsyncIterator
from uuid import UUID


class MockStorageService:
    """
    Mock storage service for testing without Supabase.
    Simulates file upload, download, and deletion.
    """

    def __init__(self):
        self.files: Dict[str, Dict[str, Any]] = {}
        self.upload_count = 0
        self.delete_count = 0

    async def upload_stream(
        self,
        file_obj,
        path: str,
        bucket: str,
        mime_type: str
    ) -> str:
        """
        Mock file upload.

        Args:
            file_obj: File-like object
            path: Storage path
            bucket: Storage bucket
            mime_type: MIME type

        Returns:
            Storage path
        """
        content = file_obj.read()
        file_obj.seek(0)
        self.files[path] = {
            "content": content,
            "bucket": bucket,
            "mime_type": mime_type
        }
        self.upload_count += 1
        return path

    async def get_url(
        self,
        path: str,
        bucket: str,
        private: bool = False
    ) -> Optional[str]:
        """
        Mock signed URL generation.

        Args:
            path: Storage path
            bucket: Storage bucket
            private: Whether to generate private URL

        Returns:
            Mock URL or None if file not found
        """
        if path in self.files:
            token = "private_token" if private else "public_token"
            return f"https://mock-storage.test/{bucket}/{path}?token={token}"
        return None

    def delete(self, path: str, bucket: str) -> bool:
        """
        Mock file deletion.

        Args:
            path: Storage path
            bucket: Storage bucket

        Returns:
            True if deleted, False if not found
        """
        if path in self.files:
            del self.files[path]
            self.delete_count += 1
            return True
        return False

    def get_file(self, path: str) -> Optional[bytes]:
        """Get file content by path."""
        if path in self.files:
            return self.files[path]["content"]
        return None

    def reset(self):
        """Reset all state."""
        self.files.clear()
        self.upload_count = 0
        self.delete_count = 0


class MockQueryEngine:
    """
    Mock query engine for testing without LLM calls.
    Provides predictable responses for RAG queries.
    """

    def __init__(
        self,
        default_response: str = "This is a mock response from the query engine.",
        should_fail: bool = False,
        fail_message: str = "Mock query engine failure"
    ):
        self.default_response = default_response
        self.should_fail = should_fail
        self.fail_message = fail_message
        self.queries: List[Any] = []
        self.last_response = None

    async def aquery(self, query_bundle) -> MagicMock:
        """
        Mock async query.

        Args:
            query_bundle: Query bundle with query string and filters

        Returns:
            Mock response object
        """
        if self.should_fail:
            raise Exception(self.fail_message)

        self.queries.append(query_bundle)

        response = MagicMock()
        response.response = self.default_response
        response.source_nodes = self._create_mock_source_nodes()
        self.last_response = response
        return response

    async def stream_query(
        self,
        query_str: str,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Mock streaming query.

        Args:
            query_str: Query string
            filters: Query filters
            user_id: User ID
            session_id: Session ID

        Yields:
            Response tokens
        """
        if self.should_fail:
            raise Exception(self.fail_message)

        self.queries.append({
            "query_str": query_str,
            "filters": filters,
            "user_id": user_id,
            "session_id": session_id
        })

        for word in self.default_response.split():
            yield word + " "

    def get_last_response(self):
        """Get the last response object."""
        return self.last_response

    def _create_mock_source_nodes(self) -> List[MagicMock]:
        """Create mock source nodes for citations."""
        nodes = []
        for i in range(2):
            node = MagicMock()
            node.node = MagicMock()
            node.node.text = f"Mock source text {i}"
            node.node.metadata = {
                "document_id": f"mock-doc-{i}",
                "page_number": i + 1
            }
            node.score = 0.9 - (i * 0.1)
            nodes.append(node)
        return nodes

    def set_response(self, response: str):
        """Set the response for subsequent queries."""
        self.default_response = response

    def set_failure(self, should_fail: bool, message: str = "Mock failure"):
        """Configure failure behavior."""
        self.should_fail = should_fail
        self.fail_message = message

    def reset(self):
        """Reset all state."""
        self.queries.clear()
        self.last_response = None
        self.should_fail = False


class MockLLM:
    """
    Mock LLM for testing without API calls.
    Provides predictable completions for generation tests.
    """

    def __init__(self, default_response: str = "Mock LLM response"):
        self.default_response = default_response
        self.calls: List[Dict[str, Any]] = []
        self.should_fail = False
        self.fail_message = "Mock LLM failure"

    async def acomplete(self, prompt: str, **kwargs) -> MagicMock:
        """
        Mock async completion.

        Args:
            prompt: Input prompt
            **kwargs: Additional arguments

        Returns:
            Mock completion response
        """
        if self.should_fail:
            raise Exception(self.fail_message)

        self.calls.append({"prompt": prompt, "kwargs": kwargs})

        response = MagicMock()
        response.text = self.default_response
        return response

    def complete(self, prompt: str, **kwargs) -> MagicMock:
        """
        Mock sync completion.

        Args:
            prompt: Input prompt
            **kwargs: Additional arguments

        Returns:
            Mock completion response
        """
        if self.should_fail:
            raise Exception(self.fail_message)

        self.calls.append({"prompt": prompt, "kwargs": kwargs})

        response = MagicMock()
        response.text = self.default_response
        return response

    async def astream_complete(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Mock async streaming completion."""
        if self.should_fail:
            raise Exception(self.fail_message)

        self.calls.append({"prompt": prompt, "kwargs": kwargs, "streaming": True})

        for word in self.default_response.split():
            yield word + " "

    def set_response(self, response: str):
        """Set the response for subsequent calls."""
        self.default_response = response

    def reset(self):
        """Reset all state."""
        self.calls.clear()
        self.should_fail = False


class MockVectorStore:
    """
    Mock vector store for testing without Qdrant.
    Simulates vector storage and retrieval.
    """

    def __init__(self):
        self.vectors: Dict[str, Dict[str, Any]] = {}
        self.collections: Dict[str, List[str]] = {}

    def add(
        self,
        nodes: List[Any],
        collection_name: str = "default"
    ) -> List[str]:
        """
        Mock adding vectors.

        Args:
            nodes: List of nodes to add
            collection_name: Collection name

        Returns:
            List of node IDs
        """
        if collection_name not in self.collections:
            self.collections[collection_name] = []

        node_ids = []
        for node in nodes:
            node_id = str(getattr(node, 'id_', 'mock-id'))
            self.vectors[node_id] = {
                "text": getattr(node, 'text', ''),
                "embedding": getattr(node, 'embedding', []),
                "metadata": getattr(node, 'metadata', {}),
                "collection": collection_name
            }
            self.collections[collection_name].append(node_id)
            node_ids.append(node_id)

        return node_ids

    def delete(self, node_ids: List[str]) -> bool:
        """
        Mock deleting vectors.

        Args:
            node_ids: List of node IDs to delete

        Returns:
            True if successful
        """
        for node_id in node_ids:
            if node_id in self.vectors:
                collection = self.vectors[node_id]["collection"]
                del self.vectors[node_id]
                if collection in self.collections:
                    self.collections[collection].remove(node_id)
        return True

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Mock vector query.

        Args:
            query_embedding: Query vector
            top_k: Number of results
            filters: Metadata filters

        Returns:
            List of matching documents
        """
        results = []
        for node_id, data in self.vectors.items():
            # Simple mock matching - return all if no filters
            if filters:
                match = all(
                    data["metadata"].get(k) == v
                    for k, v in filters.items()
                )
                if not match:
                    continue

            results.append({
                "id": node_id,
                "score": 0.9,  # Mock score
                "text": data["text"],
                "metadata": data["metadata"]
            })

            if len(results) >= top_k:
                break

        return results

    def reset(self):
        """Reset all state."""
        self.vectors.clear()
        self.collections.clear()


class MockDocumentIndexer:
    """
    Mock document indexer for testing.
    Simulates document indexing without vector store.
    """

    def __init__(self):
        self.indexed_documents: Dict[str, Dict[str, Any]] = {}
        self.index_count = 0
        self.delete_count = 0

    def index_document(
        self,
        processed_doc,
        replace_existing: bool = False
    ) -> List[str]:
        """
        Mock document indexing.

        Args:
            processed_doc: Processed document
            replace_existing: Whether to replace existing

        Returns:
            List of node IDs
        """
        doc_id = str(getattr(processed_doc, 'id', 'mock-doc'))

        self.indexed_documents[doc_id] = {
            "chunks": getattr(processed_doc, 'chunks', []),
            "metadata": getattr(processed_doc, 'metadata', {}),
            "chunk_count": getattr(processed_doc, 'chunk_count', 0)
        }
        self.index_count += 1

        return [f"{doc_id}-node-{i}" for i in range(5)]

    def delete_document(self, document_id: UUID) -> bool:
        """
        Mock document deletion from index.

        Args:
            document_id: Document UUID

        Returns:
            True if deleted
        """
        doc_id = str(document_id)
        if doc_id in self.indexed_documents:
            del self.indexed_documents[doc_id]
            self.delete_count += 1
            return True
        return False

    def reset(self):
        """Reset all state."""
        self.indexed_documents.clear()
        self.index_count = 0
        self.delete_count = 0


# Factory function to create mock instances
def create_mock_storage() -> MockStorageService:
    """Create a new MockStorageService instance."""
    return MockStorageService()


def create_mock_query_engine(response: str = None) -> MockQueryEngine:
    """Create a new MockQueryEngine instance."""
    return MockQueryEngine(default_response=response or "Mock response")


def create_mock_llm(response: str = None) -> MockLLM:
    """Create a new MockLLM instance."""
    return MockLLM(default_response=response or "Mock LLM response")


def create_mock_vector_store() -> MockVectorStore:
    """Create a new MockVectorStore instance."""
    return MockVectorStore()


def create_mock_indexer() -> MockDocumentIndexer:
    """Create a new MockDocumentIndexer instance."""
    return MockDocumentIndexer()
