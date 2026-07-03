from typing import List, Optional, Dict, Any
from uuid import UUID

from llama_index.core.schema import TextNode
from loguru import logger
from langfuse import observe

from src.db.vector_store import QdrantVectorStoreWrapper, get_vector_store
from src.schemas.document import UnifiedDocument, DocumentChunk
from src.config import get_settings
from src.services.observability.langfuse_config import get_langfuse_client
from src.services.observability.tracing import trace_embedding
from qdrant_client.models import Filter, FieldCondition, MatchValue

class DocumentIndexer:
    """
    Indexer for UnifiedDocument objects using LlamaIndex and Qdrant.
    
    Handles:
    - Converting UnifiedDocument to LlamaIndex nodes
    - Storing nodes in Qdrant with embeddings
    - Incremental updates (delete old, add new)
    - Batch indexing for performance
    """
    
    def __init__(
        self,
        vector_store: Optional[QdrantVectorStoreWrapper] = None,
    ):
        """
        Initialize the document indexer.
        
        Args:
            vector_store: QdrantVectorStoreWrapper instance. If None, uses singleton.
        """
        self.vector_store = vector_store or get_vector_store()
        self.settings = get_settings()
        
        self.vector_store.ensure_collection_exists()
        # Note: setup_langfuse() is called once at app startup (see app.py)

        logger.info("DocumentIndexer initialized")
    
    @observe(as_type="span", name="document_indexing")
    async def index_document(
        self,
        document: UnifiedDocument,
        replace_existing: bool = True,
    ) -> List[str]:
        """
        Index a single UnifiedDocument.
        
        Args:
            document: UnifiedDocument to index
            replace_existing: If True, delete existing nodes for this document first
            
        Returns:
            List of node IDs that were created
        """
        if not document.chunks:
            logger.warning(f"Document {document.id} has no chunks to index")
            return []
        
        if replace_existing:
            deleted_count = self.vector_store.delete_by_document_id(document.id)
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} existing nodes for document {document.id}")
        
        langfuse = get_langfuse_client()
        if langfuse:
            langfuse.update_current_span(
                metadata={
                    "document_id": str(document.id),
                    "filename": document.filename,
                    "source_type": document.source_type.value,
                    "chunk_count": len(document.chunks),
                    "tags": ["indexing", "document"],
                }
            )
            if document.user_id:
                langfuse.update_current_trace(user_id=str(document.user_id))

      
        nodes = self._convert_chunks_to_nodes(document)
        
        if not nodes:
            logger.warning(f"No nodes created for document {document.id}")
            return []
        
        trace_embedding(
            text_count=len(nodes),
            embedding_dim=self.settings.embedding.dimension,
            metadata={
                "document_id": str(document.id),
                "filename": document.filename,
                "source_type": document.source_type.value,
                "chunk_count": len(document.chunks),
            },
            user_id=str(document.user_id) if document.user_id else None,
        )
        
  
        node_ids = await self.vector_store.add_nodes(nodes)
        
        if langfuse:
            langfuse.update_current_span(
                metadata={
                    "nodes_created": len(node_ids),
                    "document_id": str(document.id),
                }
            )
        
        logger.info(
            f"Indexed document {document.id} ({document.filename}): "
            f"{len(node_ids)} nodes added"
        )
        
        return node_ids
    
    async def index_documents(
        self,
        documents: List[UnifiedDocument],
        replace_existing: bool = True,
        batch_size: int = 10,
    ) -> Dict[UUID, List[str]]:
        """
        Index multiple documents in batch.
        
        Args:
            documents: List of UnifiedDocument objects to index
            replace_existing: If True, delete existing nodes for each document first
            batch_size: Number of documents to process in each batch
            
        Returns:
            Dictionary mapping document IDs to lists of node IDs
        """
        if not documents:
            return {}
        
        results: Dict[UUID, List[str]] = {}
        
        logger.info(f"Starting batch indexing of {len(documents)} documents")
        
     
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            for document in batch:
                try:
                    node_ids = await self.index_document(document, replace_existing=replace_existing)
                    results[document.id] = node_ids
                except Exception as e:
                    logger.error(
                        f"Failed to index document {document.id}: {e}",
                        exc_info=True
                    )
                    results[document.id] = []
            
            logger.debug(f"Processed batch {i // batch_size + 1}/{(len(documents) + batch_size - 1) // batch_size}")
        
        total_nodes = sum(len(node_ids) for node_ids in results.values())
        logger.info(
            f"Batch indexing complete: {len(results)} documents, "
            f"{total_nodes} total nodes indexed"
        )
        
        return results
    
    async def update_document(
        self,
        document: UnifiedDocument,
    ) -> List[str]:
        """
        Update an existing document in the index.
        
        This is equivalent to index_document with replace_existing=True.
        
        Args:
            document: Updated UnifiedDocument
            
        Returns:
            List of node IDs that were created
        """
        return await self.index_document(document, replace_existing=True)
    
    def delete_document(
        self,
        document_id: UUID,
    ) -> int:
        """
        Delete all nodes for a document from the index.
        
        Args:
            document_id: UUID of the document to delete
            
        Returns:
            Number of nodes deleted
        """
        deleted_count = self.vector_store.delete_by_document_id(document_id)
        
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} nodes for document {document_id}")
        else:
            logger.debug(f"No nodes found for document {document_id}")
        
        return deleted_count
    
    def delete_documents(
        self,
        document_ids: List[UUID],
    ) -> Dict[UUID, int]:
        """
        Delete multiple documents from the index.
        
        Args:
            document_ids: List of document UUIDs to delete
            
        Returns:
            Dictionary mapping document IDs to number of nodes deleted
        """
        results: Dict[UUID, int] = {}
        
        for document_id in document_ids:
            try:
                deleted_count = self.delete_document(document_id)
                results[document_id] = deleted_count
            except Exception as e:
                logger.error(
                    f"Failed to delete document {document_id}: {e}",
                    exc_info=True
                )
                results[document_id] = 0
        
        return results
    
    def _convert_chunks_to_nodes(
        self,
        document: UnifiedDocument,
    ) -> List[TextNode]:
        """
        Convert UnifiedDocument chunks to LlamaIndex TextNode objects.
        
        Args:
            document: UnifiedDocument to convert
            
        Returns:
            List of TextNode objects
        """
        nodes: List[TextNode] = []
        
        for chunk in document.chunks:
            
            metadata = self._build_node_metadata(document, chunk)

            node = TextNode(
                text=chunk.content,
                metadata=metadata,
                node_id=chunk.chunk_id,  
            )
            
            nodes.append(node)
        
        return nodes
    
    def _build_node_metadata(
        self,
        document: UnifiedDocument,
        chunk: DocumentChunk,
    ) -> Dict[str, Any]:
        """
        Build metadata dictionary for a node from document and chunk.
        
        Args:
            document: Parent UnifiedDocument
            chunk: DocumentChunk
            
        Returns:
            Metadata dictionary
        """
      
        metadata: Dict[str, Any] = {
        
            "document_id": str(document.id),
            "user_id": str(document.user_id),
            "filename": document.filename,
            "source_type": document.source_type.value,
            
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.chunk_index,
        }
        
        # Add notebook_id from document metadata if present (for notebook-level filtering)
        if document.metadata and "notebook_id" in document.metadata:
            metadata["notebook_id"] = str(document.metadata["notebook_id"])
        
        if chunk.page_number is not None:
            metadata["page_number"] = chunk.page_number
        
        if chunk.start_time is not None:
            metadata["start_time"] = chunk.start_time
        
        if chunk.end_time is not None:
            metadata["end_time"] = chunk.end_time
        
        return metadata
    
    def get_document_node_count(
        self,
        document_id: UUID,
    ) -> int:
        """
        Get the number of nodes indexed for a document.
        
        Args:
            document_id: UUID of the document
            
        Returns:
            Number of nodes
        """
    
        try:
            document_id_str = str(document_id)
            count_filter = Filter(
                must=[
                    FieldCondition(
                        key="metadata.document_id",
                        match=MatchValue(value=document_id_str),
                    )
                ]
            )
            
            result = self.vector_store.client.count(
                collection_name=self.vector_store.collection_name,
                count_filter=count_filter,
            )
            
            return result.count
        except Exception as e:
            logger.warning(f"Failed to count nodes for document {document_id}: {e}")
            return 0
    
    async def reindex_document(
        self,
        document: UnifiedDocument,
    ) -> List[str]:
        """
        Reindex a document (delete and re-add).
        
        Args:
            document: UnifiedDocument to reindex
            
        Returns:
            List of node IDs that were created
        """
        logger.info(f"Reindexing document {document.id}")
        
       
        self.delete_document(document.id)
        
      
        return await self.index_document(document, replace_existing=False)
    
    async def index_if_needed(
        self,
        document: UnifiedDocument,
        force: bool = False,
    ) -> Optional[List[str]]:
        """
        Index a document only if it hasn't been indexed or if force=True.
        
        Args:
            document: UnifiedDocument to index
            force: If True, reindex even if already indexed
            
        Returns:
            List of node IDs if indexed, None if skipped
        """
      
        if not force:
            node_count = self.get_document_node_count(document.id)
            if node_count > 0:
                logger.debug(
                    f"Document {document.id} already indexed ({node_count} nodes), skipping"
                )
                return None
   
        return await self.index_document(document, replace_existing=force)



_indexer_instance: Optional[DocumentIndexer] = None


def get_indexer() -> DocumentIndexer:
    """
    Get or create the singleton indexer instance.
    
    Returns:
        DocumentIndexer instance
    """
    global _indexer_instance
    
    if _indexer_instance is None:
        _indexer_instance = DocumentIndexer()
    
    return _indexer_instance
