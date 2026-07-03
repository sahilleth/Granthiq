import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any
from uuid import UUID
import uuid

import numpy as np
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.schema import Document as LIDocument, TextNode
from src.services.embeddings.embedding_config import configure_llamaindex_embed_model , get_llamaindex_embed_model
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    CollectionInfo,
    SparseVectorParams,
    SparseIndexParams,
    PayloadSchemaType,
)
from sentence_transformers import SentenceTransformer
from loguru import logger
from qdrant_client.http.exceptions import UnexpectedResponse

from src.config import get_settings
from src.schemas.document import DocumentType
from dotenv import load_dotenv

# Import cache for query embeddings
from src.utils.cache import get_query_embedding_cache

# Thread pool for CPU-bound embedding operations
_embedding_executor = None

def _get_embedding_executor() -> ThreadPoolExecutor:
    """Get or create thread pool executor for embedding operations."""
    global _embedding_executor
    if _embedding_executor is None:
        _embedding_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="embedding_"
        )
    return _embedding_executor

load_dotenv()

class QdrantVectorStoreWrapper:
   
    
    def __init__(
        self,
        collection_name: Optional[str] = None,
        embedding_model: Optional[SentenceTransformer] = None,
        qdrant_client: Optional[QdrantClient] = None,
    ):
        """
        Initialize Qdrant vector store wrapper.
        
        Args:
            collection_name: Name of the Qdrant collection. If None, uses config default.
            embedding_model: SentenceTransformer model for embeddings. If None, loads from config.
            qdrant_client: Qdrant client instance. If None, creates from config.
        """
        settings = get_settings()
        
       
        if qdrant_client is None:
            qdrant_host = settings.qdrant.host
            api_key = settings.qdrant.api_key
            
           
            if not qdrant_host or str(qdrant_host) == "None" or str(qdrant_host) == ":memory:":
                logger.warning("Using persistent local storage at ./qdrant_data because QDRANT_HOST is not set or memory.")
                self.client = QdrantClient(path="./qdrant_data")
                self.aclient = None
                qdrant_url = None
            else:
                qdrant_url = str(qdrant_host)
                
                
                if "cloud.qdrant.io" in qdrant_url and not api_key:
                    logger.critical("Attempting to connect to Qdrant Cloud without an API Key.")
                    raise ValueError(
                        "QDRANT_API_KEY is missing. You are using a Qdrant Cloud URL "
                        "but have not provided an API key in your .env file."
                    )
                # Sync client: Used by LlamaIndex (QdrantVectorStore requires sync client)
                self.client = QdrantClient(
                    url=qdrant_url,
                    api_key=api_key,
                    timeout=60.0,
                )
                # Async client: Used for direct async operations (health checks, etc.)
                self.aclient = AsyncQdrantClient(
                    url=qdrant_url,
                    api_key=api_key,
                    timeout=60.0,
                )
        else:
            self.client = qdrant_client
            
            qdrant_host = settings.qdrant.host
            if qdrant_host and str(qdrant_host) != "None" and str(qdrant_host) != ":memory:":
                qdrant_url = str(qdrant_host)
                api_key = settings.qdrant.api_key
                self.aclient = AsyncQdrantClient(
                    url=qdrant_url,
                    api_key=api_key,
                    timeout=60.0,
                )
            else:
                self.aclient = None

        self.collection_name = collection_name or settings.qdrant.collection_name
        if not self.collection_name:
            self.collection_name = "notebookllm_collection"
            logger.warning(
                f"Collection name not set in config, using default: {self.collection_name}"
            )
        
        logger.info(f"Using Qdrant collection: {self.collection_name}")
        
        # Initialize embedding model
        # Use LlamaIndex's configured embed_model instead of SentenceTransformer
        # to avoid meta tensor issues and ensure consistency
        if embedding_model is None:
           
            
            
            # Configure embed_model first (this sets Settings.embed_model)
            configure_llamaindex_embed_model()
            
            # Get the LlamaIndex embed model (HuggingFaceEmbedding)
            embed_model = get_llamaindex_embed_model()
            
            # Store reference to embed_model for encoding
            self.embed_model = embed_model
            self.embedding_dimension = settings.embedding.dimension
            
            # For backward compatibility, we'll use embed_model.get_query_embedding
            # instead of SentenceTransformer.encode
            self.embedding_model = None  # Mark that we're using LlamaIndex embed model
            logger.info(f"Using LlamaIndex embed_model: {settings.embedding.model}")
        else:
            # Legacy: if SentenceTransformer is provided, use it
            self.embedding_model = embedding_model
            self.embed_model = None
            self.embedding_dimension = self.embedding_model.get_sentence_embedding_dimension()
        
       

        
        # Ensure collection exists before initializing QdrantVectorStore
        # This prevents 403 errors when QdrantVectorStore tries to check collection existence
        logger.info(f"Ensuring collection '{self.collection_name}' exists...")
        try:
            self._ensure_collection_exists()
        except UnexpectedResponse as e:
            if "404 page not found" in str(e) or (hasattr(e, 'content') and b"404 page not found" in e.content):
                logger.critical(f"Invalid Qdrant Cloud URL: {qdrant_url}. The server returned '404 page not found'.")
                raise ValueError(
                    f"Unable to connect to Qdrant Cloud at {qdrant_url}. "
                    "The server returned '404 page not found', which usually means the Cluster URL is incorrect "
                    "or the cluster has been deleted. Please verify your QDRANT_HOST in .env."
                ) from e
            raise
        except Exception as e:
            logger.error(
                f"Failed to create/verify collection '{self.collection_name}': {e}\n"
                f"Please check your QDRANT_API_KEY has permissions to create collections."
            )
            raise
        
        # Initialize LlamaIndex vector store with hybrid search enabled (BM42)
        # BM42 is faster and more accurate than BM25 for sparse embeddings
        # Only pass aclient if not using :memory: mode to avoid sync warnings
        vector_store_kwargs = {
            "client": self.client,
            "collection_name": self.collection_name,
            "enable_hybrid": True,  # Enable native hybrid search
            "fastembed_sparse_model": "Qdrant/bm42-all-minilm-l6-v2-attentions",  # Use BM42 for sparse vectors
            "batch_size": 20,  # Batch size for sparse vector generation
        }
        
        # Only add aclient if not using :memory: mode (which causes sync issues)
        # For Qdrant Cloud, we need both client and aclient, but they're properly synced
        # Check if we have an aclient configured
        if hasattr(self, 'aclient') and self.aclient is not None:
            vector_store_kwargs["aclient"] = self.aclient
        
        logger.info(f"Initializing QdrantVectorStore with collection: {self.collection_name}")
        
        # Initialize QdrantVectorStore - collection should exist now
        try:
            self.vector_store = QdrantVectorStore(**vector_store_kwargs)
        except AttributeError as e:
            if "__pydantic_private__" in str(e):
                logger.error("Pydantic v2 compatibility issue detected with LlamaIndex QdrantVectorStore.")
                logger.error("Fix: Use a newer version of llama-index-vector-stores-qdrant or downgrade pydantic.")
                logger.warning("Vector store will be unavailable. Basic CRUD endpoints will still work.")
                self.vector_store = None
                self.storage_context = None
                return
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Failed to initialize QdrantVectorStore: {error_msg}\n"
                f"Collection '{self.collection_name}' should exist, but there may be a configuration issue."
            )
            logger.warning("Vector store will be unavailable. Basic CRUD endpoints will still work.")
            self.vector_store = None
            self.storage_context = None
            return
        
        # Storage context for LlamaIndex
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )
        
        logger.info(
            f"QdrantVectorStoreWrapper initialized: "
            f"collection={self.collection_name}, "
            f"embedding_dim={self.embedding_dimension}, "
            f"sparse_model=BM42"
        )
    
    def _ensure_collection_exists(self) -> None:
        """
        Internal method to ensure the Qdrant collection exists with hybrid search support.
        Creates collection with both dense and sparse vectors if it doesn't exist.
        """
        try:
            collection_info = self.client.get_collection(self.collection_name)
            logger.info(f"Collection '{self.collection_name}' already exists")
            # Check if it has sparse vectors configured
            # Qdrant stores sparse vectors in config.params.sparse_vectors
            has_sparse = False
            if hasattr(collection_info.config, 'params') and hasattr(collection_info.config.params, 'sparse_vectors'):
                sparse_vectors = collection_info.config.params.sparse_vectors
                # Check if sparse_vectors is a dict/map with content
                if sparse_vectors and hasattr(sparse_vectors, 'map') and sparse_vectors.map:
                    has_sparse = True
                elif isinstance(sparse_vectors, dict) and sparse_vectors:
                    has_sparse = True
            
            if not has_sparse:
                logger.warning(
                    f"Collection '{self.collection_name}' exists but doesn't have sparse vectors. "
                    "Hybrid search may not work properly. Consider recreating the collection."
                )
            
            # Ensure document_id index exists for efficient filtering
            try:
                # Try to create the index - it will fail silently if it already exists
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="metadata.document_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.info("Created payload index on 'metadata.document_id' field")
            except Exception as index_err:
                # Index might already exist, which is fine
                error_str = str(index_err).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.debug("Index on 'metadata.document_id' already exists")
                else:
                    logger.warning(f"Could not ensure index on 'metadata.document_id': {index_err}")
            
            # CRITICAL FIX: Ensure user_id index exists (required for strict filtering)
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="metadata.user_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.info("Created payload index on 'metadata.user_id' field")
            except Exception as index_err:
                error_str = str(index_err).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.debug("Index on 'metadata.user_id' already exists")
                else:
                    logger.warning(f"Could not ensure index on 'metadata.user_id': {index_err}")

            # Ensure notebook_id index exists for strict per-notebook filtering
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="metadata.notebook_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.info("Created payload index on 'metadata.notebook_id' field")
            except Exception as index_err:
                error_str = str(index_err).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.debug("Index on 'metadata.notebook_id' already exists")
                else:
                    logger.warning(f"Could not ensure index on 'metadata.notebook_id': {index_err}")
            
            # Ensure source_type index exists for filtering by source type (e.g., fiqa_dataset, pdf, etc.)
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="metadata.source_type",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.info("Created payload index on 'metadata.source_type' field")
            except Exception as index_err:
                error_str = str(index_err).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.debug("Index on 'metadata.source_type' already exists")
                else:
                    logger.warning(f"Could not ensure index on 'metadata.source_type': {index_err}")
        except Exception as e:
    
            error_str = str(e).lower()
            if "not found" in error_str or "404" in error_str or "does not exist" in error_str:
                logger.info(f"Collection '{self.collection_name}' does not exist. Creating it with hybrid search support...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "text-dense": VectorParams( 
                            size=self.embedding_dimension,
                            distance=Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        "text-sparse": SparseVectorParams(  
                            index=SparseIndexParams()
                        )
                    },
                )
                logger.info(
                    f"Collection '{self.collection_name}' created successfully "
                    "with dense and sparse vectors for hybrid search (BM42)"
                )
                # Create index on document_id field for efficient filtering
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="metadata.document_id",
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                    logger.info("Created payload index on 'metadata.document_id' field")
                except Exception as index_err:
                    logger.warning(f"Failed to create index on 'metadata.document_id': {index_err}")
                
                # Create index on user_id field
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="metadata.user_id",
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                    logger.info("Created payload index on 'metadata.user_id' field")
                except Exception as index_err:
                    logger.warning(f"Failed to create index on 'metadata.user_id': {index_err}")

                # Create index on notebook_id field (required for notebook-scoped queries)
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="metadata.notebook_id",
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                    logger.info("Created payload index on 'metadata.notebook_id' field")
                except Exception as index_err:
                    logger.warning(f"Failed to create index on 'metadata.notebook_id': {index_err}")
                
                # Create index on source_type field (required for filtering by source type, e.g., fiqa_dataset)
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="metadata.source_type",
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                    logger.info("Created payload index on 'metadata.source_type' field")
                except Exception as index_err:
                    logger.warning(f"Failed to create index on 'metadata.source_type': {index_err}")

            else:
                raise
    
    def ensure_collection_exists(self) -> None:
        
        self._ensure_collection_exists()
    
    def delete_collection(self) -> bool:
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Collection '{self.collection_name}' deleted")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete collection: {e}")
            return False
    
    def collection_exists(self) -> bool:
        try:
            self.client.get_collection(self.collection_name)
            return True
        except UnexpectedResponse as e:
            logger.debug(f"Collection '{self.collection_name}' does not exist: {e}")
            return False
    
    def get_collection_info(self) -> Optional[CollectionInfo]:
        try:
            return self.client.get_collection(self.collection_name)
        except UnexpectedResponse as e:
            logger.debug(f"Could not get collection info for '{self.collection_name}': {e}")
            return None
    
    async def add_nodes(
        self,
        nodes: List[TextNode],
        batch_size: int = 100,
    ) -> List[str]:
        """
        Add nodes to the vector store.
        
        Args:
            nodes: List of TextNode objects to add
            batch_size: Number of nodes to process in each batch
            
        Returns:
            List of node IDs that were added
        """
        if not nodes:
            return []
        
        self.ensure_collection_exists()
        
        # Get the actual collection configuration to determine vector name
        vector_name = None
        try:
            collection_info = self.client.get_collection(self.collection_name)
            vectors_config = collection_info.config.params.vectors
            
            # Handle different vector config structures
            if vectors_config is None:
                # No vectors config - use default
                vector_name = None
            elif hasattr(vectors_config, 'map') and vectors_config.map:
                # NamedVectors with map attribute
                vector_name = list(vectors_config.map.keys())[0]
            elif hasattr(vectors_config, '__dict__'):
                # Try to access as object with attributes
                if hasattr(vectors_config, 'size'):
                    # Single unnamed vector
                    vector_name = None
                else:
                    # Try to get keys from dict-like object
                    try:
                        vector_name = list(vectors_config.keys())[0] if hasattr(vectors_config, 'keys') else None
                    except (TypeError, AttributeError) as e:
                        logger.debug(f"Could not extract vector name from config: {e}")
                        vector_name = None
            elif isinstance(vectors_config, dict) and vectors_config:
                # Named vectors as dict
                vector_name = list(vectors_config.keys())[0]
            else:
                # Single unnamed vector or unknown structure
                vector_name = None
            
            logger.debug(f"Detected vector name: {vector_name or 'default (unnamed)'}")
        except Exception as e:
            logger.warning(f"Could not determine vector name from collection: {e}. Defaulting to 'text-dense'")
            vector_name = "text-dense"
        
        node_ids = []
        
        
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            
            
            texts = [node.text for node in batch]
            
 
            if self.embedding_model is None and self.embed_model is not None:
               
                # Use asyncio.to_thread for non-blocking embedding generation
                # This prevents blocking the event loop during CPU-intensive embedding
                embeddings_list = await asyncio.gather(*[
                    asyncio.to_thread(self.embed_model.get_text_embedding, text)
                    for text in texts
                ])
                embeddings = np.array(embeddings_list)
            else:
                # Run SentenceTransformer.encode in thread pool to avoid blocking
                embeddings = await asyncio.to_thread(
                    self.embedding_model.encode,
                    texts,
                    show_progress_bar=False,  # Disabled for async context
                    convert_to_numpy=True,
                )
            
            # Prepare points for Qdrant
            points = []
            for node, embedding in zip(batch, embeddings):
                # Ensure node has an ID
                if node.node_id is None:
                    node.node_id = str(uuid.uuid4())
                
                # Prepare payload with text and metadata
                payload = self._prepare_payload(node.text, node.metadata)
                
                # Format vector based on whether it's named or not
                if vector_name and vector_name.strip():
                    # Named vector - use dict format
                    vector_data = {vector_name: embedding.tolist()}
                else:
                    # Unnamed/default vector - use list directly
                    # But if collection has named vectors, we need to use a name
                    # Try "text-dense" as fallback
                    try:
                        collection_info = self.client.get_collection(self.collection_name)
                        vectors_config = collection_info.config.params.vectors
                        # If vectors_config exists and is not None, it likely has named vectors
                        if vectors_config is not None:
                            vector_data = {"text-dense": embedding.tolist()}
                        else:
                            vector_data = embedding.tolist()
                    except UnexpectedResponse as e:
                        logger.debug(f"Could not get collection info for vector format: {e}")
                        # Fallback: try named first, then unnamed
                        vector_data = {"text-dense": embedding.tolist()}
                
                points.append(
                    PointStruct(
                        id=node.node_id,
                        vector=vector_data,
                        payload=payload,
                    )
                )
            
            # Insert points into Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            
            node_ids.extend([node.node_id for node in batch])
            logger.debug(f"Added batch of {len(batch)} nodes to collection")
        
        logger.info(f"Added {len(node_ids)} nodes to collection '{self.collection_name}'")
        return node_ids
    
    async def add_documents(
        self,
        documents: List[LIDocument],
        batch_size: int = 100,
    ) -> List[str]:
        """
        Add documents to the vector store.
        
        This converts documents to nodes and adds them.
        
        Args:
            documents: List of LlamaIndex Document objects
            batch_size: Number of documents to process in each batch
            
        Returns:
            List of node IDs that were created
        """
        if not documents:
            return []
        
        # Convert documents to nodes
        nodes = []
        for doc in documents:
            node = TextNode(
                text=doc.text,
                metadata=doc.metadata or {},
            )
            nodes.append(node)
        
        return await self.add_nodes(nodes, batch_size=batch_size)
    
    def delete_nodes(
        self,
        node_ids: List[str],
    ) -> None:
        """
        Delete nodes from the vector store.
        
        Args:
            node_ids: List of node IDs to delete
        """
        if not node_ids:
            return
        
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=node_ids,
        )
        logger.info(f"Deleted {len(node_ids)} nodes from collection")
    
    def delete_by_document_id(
        self,
        document_id: UUID,
    ) -> int:
        """
        Delete all nodes associated with a document ID.
        
        Args:
            document_id: UUID of the document
            
        Returns:
            Number of nodes deleted
        """
        # Ensure index exists before filtering
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="metadata.document_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as index_err:
            # Index might already exist, which is fine
            error_str = str(index_err).lower()
            if "already exists" not in error_str and "duplicate" not in error_str:
                logger.warning(f"Could not create index on 'metadata.document_id': {index_err}")
        
        # Search for all points with this document_id
        document_id_str = str(document_id)
        
        # Use scroll to find all matching points
        points_to_delete = []
        offset = None
        
        try:
            while True:
                result, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="metadata.document_id",
                                match=MatchValue(value=document_id_str),
                            )
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                
                if not result:
                    break
                
                points_to_delete.extend([point.id for point in result])
                
                if offset is None:
                    break
        except Exception as e:
            error_str = str(e).lower()
            if "index required" in error_str or "not found" in error_str:
                logger.error(
                    f"Index on 'metadata.document_id' is required but not found. "
                    f"Please create it manually or wait for automatic creation. Error: {e}"
                )
                # Try to create the index and retry once
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="metadata.document_id",
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                    logger.info("Created index on 'metadata.document_id', retrying delete operation")
                    # Retry the scroll operation
                    return self.delete_by_document_id(document_id)
                except Exception as retry_err:
                    logger.error(f"Failed to create index and retry: {retry_err}")
                    raise
            else:
                raise
        
        if points_to_delete:
            self.delete_nodes(points_to_delete)
        
        return len(points_to_delete)
    
    def _prepare_payload(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare payload for Qdrant storage.
        
        Qdrant requires certain types for filtering. This converts metadata
        to Qdrant-compatible format and includes the text.
        
        Args:
            text: Node text content
            metadata: Original metadata dictionary
            
        Returns:
            Prepared payload dictionary with 'text' and 'metadata' keys
        """
        prepared = {
            "text": text,
            "metadata": {},
        }
        
        # Convert all metadata values to strings for filtering compatibility
        for key, value in metadata.items():
            # Convert to string for Qdrant filtering
            if isinstance(value, (str, int, float, bool)):
                prepared["metadata"][key] = str(value)
            elif isinstance(value, UUID):
                prepared["metadata"][key] = str(value)
            elif isinstance(value, list):
                prepared["metadata"][key] = [str(v) for v in value]
            elif value is None:
                prepared["metadata"][key] = None
            else:
                prepared["metadata"][key] = str(value)
        
        return prepared
    
    def _build_qdrant_filter(self, filters: Dict[str, Any]) -> Optional[Filter]:
        """
        Build Qdrant filter from metadata filters.
        
        Args:
            filters: Dictionary of metadata filters
            
        Returns:
            Qdrant Filter object or None
        """
        if not filters:
            return None
        
        must_conditions = []
        should_groups = {}
        
        for key, value in filters.items():
            
            if isinstance(value, list) and len(value) > 1:
                
                list_conditions = [
                    FieldCondition(
                        key=f"metadata.{key}",
                        match=MatchValue(value=str(v)),
                    )
                    for v in value
                ]
                should_groups[key] = list_conditions
            else:
                # Single value condition
                single_value = value[0] if isinstance(value, list) and len(value) == 1 else value
                # Prevent double prefixing if key already starts with metadata.
                field_key = key if key.startswith("metadata.") else f"metadata.{key}"
                
                must_conditions.append(
                    FieldCondition(
                        key=field_key,
                        match=MatchValue(value=str(single_value)),
                    )
                )
        
        if should_groups and must_conditions:
            # Both must and should conditions
            should_list = []
            for key, conditions in should_groups.items():
                should_list.extend(conditions)
            return Filter(
                must=must_conditions,
                should=should_list,
                min_should=1 if should_list else 0,
            )
        elif should_groups:
            # Only should conditions
            should_list = []
            for key, conditions in should_groups.items():
                should_list.extend(conditions)
            return Filter(
                should=should_list,
                min_should=1,
            )
        elif must_conditions:
            # Only must conditions
            return Filter(must=must_conditions)
        
        return None
    
    def _build_qdrant_filter_from_li_filters(self, filters: Any) -> Optional[Filter]:
        """
        Build Qdrant filter from LlamaIndex filter objects.
        
        Args:
            filters: LlamaIndex filter object
            
        Returns:
            Qdrant Filter object or None
        """
        
        if hasattr(filters, "metadata_filters"):
            metadata_filters = filters.metadata_filters
            filter_dict = {}
            for mf in metadata_filters:
                filter_dict[mf.key] = mf.value
            return self._build_qdrant_filter(filter_dict)
        
        return None
    
    def get_index(self) -> VectorStoreIndex:
        """
        Get or create a VectorStoreIndex for this vector store.
        
        Returns:
            VectorStoreIndex instance
        """

        
        # Try to load existing index
        try:
            index = VectorStoreIndex.from_vector_store(
                vector_store=self.vector_store,
                storage_context=self.storage_context,
            )
            return index
        except (ValueError, RuntimeError) as e:
            logger.warning(f"Could not load existing index, creating new one: {e}")
            index = VectorStoreIndex.from_vector_store(
                vector_store=self.vector_store,
                storage_context=self.storage_context,
            )
            return index



_vector_store_instance: Optional[QdrantVectorStoreWrapper] = None


def get_vector_store() -> QdrantVectorStoreWrapper:
    """
    Get or create the singleton vector store instance.
    
    Returns:
        QdrantVectorStoreWrapper instance
    """
    global _vector_store_instance
    
    if _vector_store_instance is None:
        _vector_store_instance = QdrantVectorStoreWrapper()
    
    return _vector_store_instance

