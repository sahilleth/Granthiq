"""
Unit tests for MainProcessor (Document Ingestion)

Tests the document ingestion functionality including:
- File processing (PDF, TXT, DOCX)
- URL processing (Web pages)
- YouTube processing
- Chunking strategies
- Database status updates
- Error handling
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID
from pathlib import Path
from datetime import datetime, timezone

from src.services.ingestion.main_processor import MainProcessor
from src.schemas.document import UnifiedDocument, DocumentType, DocumentChunk, ProcessingStatusEnum
from src.db.models import ProcessingStatus


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.rag = Mock()
    settings.rag.chunk_size = 1000
    settings.rag.chunk_overlap = 200
    settings.rag.chunking_strategy = "sentence"
    settings.embedding = Mock()
    settings.embedding.model = "all-MiniLM-L6-v2"
    settings.assemblyai = Mock()
    settings.assemblyai.api_key = "test-assemblyai-key"
    settings.firecrawl = Mock()
    settings.firecrawl.api_key = "test-firecrawl-key"
    return settings


@pytest.fixture
def sample_unified_document():
    """Sample unified document for testing."""
    doc_id = uuid4()
    return UnifiedDocument(
        id=doc_id,
        title="Test Document",
        source_type=DocumentType.PDF,
        source_path="test/path/document.pdf",
        content="This is test content from the document.",
        status=ProcessingStatusEnum.COMPLETED,
        chunks=[
            DocumentChunk(
                chunk_id=f"{doc_id}_chunk_0",
                document_id=doc_id,
                content="This is the first chunk of content.",
                chunk_index=0,
                metadata={"page": 1}
            ),
            DocumentChunk(
                chunk_id=f"{doc_id}_chunk_1",
                document_id=doc_id,
                content="This is the second chunk of content.",
                chunk_index=1,
                metadata={"page": 1}
            ),
            DocumentChunk(
                chunk_id=f"{doc_id}_chunk_2",
                document_id=doc_id,
                content="This is the third chunk of content.",
                chunk_index=2,
                metadata={"page": 2}
            )
        ],
        metadata={"pages": 2}
    )


class TestMainProcessor:
    """Test suite for MainProcessor."""

    def test_initialization(self, mock_settings):
        """Test MainProcessor initializes correctly."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            assert processor.chunk_size == 1000
                            assert processor.chunk_overlap == 200

    def test_initialization_with_custom_params(self, mock_settings):
        """Test MainProcessor with custom chunk parameters."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor(
                                chunk_size=500,
                                chunk_overlap=100
                            )

                            assert processor.chunk_size == 500
                            assert processor.chunk_overlap == 100

    def test_detect_document_type_pdf(self, mock_settings):
        """Test document type detection for PDF files."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            doc_type = processor._detect_document_type(Path("test.pdf"))
                            assert doc_type == DocumentType.PDF

    def test_detect_document_type_txt(self, mock_settings):
        """Test document type detection for TXT files."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            doc_type = processor._detect_document_type(Path("test.txt"))
                            assert doc_type == DocumentType.TXT

    def test_detect_document_type_docx(self, mock_settings):
        """Test document type detection for DOCX files."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            doc_type = processor._detect_document_type(Path("test.docx"))
                            assert doc_type == DocumentType.DOCX

    def test_detect_document_type_audio(self, mock_settings):
        """Test document type detection for audio files."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            for ext in ['.mp3', '.wav', '.m4a', '.ogg']:
                                doc_type = processor._detect_document_type(Path(f"test{ext}"))
                                assert doc_type == DocumentType.AUDIO

    def test_detect_document_type_unknown(self, mock_settings):
        """Test document type detection for unknown files."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            doc_type = processor._detect_document_type(Path("test.xyz"))
                            assert doc_type == DocumentType.UNKNOWN

    @pytest.mark.asyncio
    async def test_process_file_pdf(self, mock_settings, sample_unified_document):
        """Test processing a PDF file."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor') as mock_doc_processor:
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.async_session_factory'):
                                with patch('src.services.ingestion.main_processor.apply_chunking_to_document_non_destructive') as mock_chunking:
                                    with patch.object(Path, 'exists', return_value=True):
                                        # Setup mocks
                                        mock_doc_processor_instance = mock_doc_processor.return_value
                                        mock_doc_processor_instance.process = AsyncMock(return_value=sample_unified_document)
                                        mock_chunking.return_value = sample_unified_document

                                        processor = MainProcessor()

                                        # Process file
                                        result = await processor.process_file(
                                            file_path=Path("test.pdf"),
                                            user_id=uuid4(),
                                            storage_path="storage/test.pdf"
                                        )

                                        # Verify
                                        assert result is not None
                                        assert result.id == sample_unified_document.id
                                        mock_doc_processor_instance.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_file_not_found(self, mock_settings):
        """Test processing a file that doesn't exist."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.async_session_factory'):
                                with patch.object(Path, 'exists', return_value=False):
                                    processor = MainProcessor()

                                    # Should raise error for non-existent file
                                    from src.utils.exceptions import DocumentProcessingError
                                    with pytest.raises(DocumentProcessingError):
                                        await processor.process_file(
                                            file_path=Path("nonexistent.pdf"),
                                            user_id=uuid4()
                                        )

    @pytest.mark.asyncio
    async def test_process_url(self, mock_settings, sample_unified_document):
        """Test processing a web URL."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor') as mock_web_processor:
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.async_session_factory'):
                                with patch('src.services.ingestion.main_processor.apply_chunking_to_document_non_destructive') as mock_chunking:
                                    # Setup mocks
                                    mock_web_processor_instance = mock_web_processor.return_value
                                    mock_web_processor_instance.process_url = Mock(return_value=sample_unified_document)
                                    mock_chunking.return_value = sample_unified_document

                                    processor = MainProcessor()

                                    # Process URL
                                    result = await processor.process_url(
                                        url="https://example.com/article",
                                        user_id=uuid4()
                                    )

                                    # Verify
                                    assert result is not None
                                    mock_web_processor_instance.process_url.assert_called_once_with("https://example.com/article")

    @pytest.mark.asyncio
    async def test_process_youtube(self, mock_settings, sample_unified_document):
        """Test processing a YouTube video."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor') as mock_yt_processor:
                            with patch('src.services.ingestion.main_processor.async_session_factory'):
                                with patch('src.services.ingestion.main_processor.apply_chunking_to_document_non_destructive') as mock_chunking:
                                    # Setup mocks
                                    mock_yt_processor_instance = mock_yt_processor.return_value
                                    mock_yt_processor_instance.process_video = AsyncMock(return_value=sample_unified_document)
                                    mock_chunking.return_value = sample_unified_document

                                    processor = MainProcessor()

                                    # Process YouTube
                                    result = await processor.process_youtube(
                                        youtube_url="https://youtube.com/watch?v=test123",
                                        user_id=uuid4()
                                    )

                                    # Verify
                                    assert result is not None
                                    mock_yt_processor_instance.process_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_batch(self, mock_settings, sample_unified_document):
        """Test batch processing multiple files."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor') as mock_doc_processor:
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.async_session_factory'):
                                with patch('src.services.ingestion.main_processor.apply_chunking_to_document_non_destructive') as mock_chunking:
                                    with patch.object(Path, 'exists', return_value=True):
                                        # Setup mocks
                                        mock_doc_processor_instance = mock_doc_processor.return_value
                                        mock_doc_processor_instance.process = AsyncMock(return_value=sample_unified_document)
                                        mock_chunking.return_value = sample_unified_document

                                        processor = MainProcessor()

                                        # Process batch
                                        file_paths = [
                                            Path("doc1.pdf"),
                                            Path("doc2.pdf"),
                                            Path("doc3.txt")
                                        ]
                                        results = await processor.process_batch(
                                            file_paths=file_paths,
                                            user_id=uuid4()
                                        )

                                        # Verify
                                        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_update_db_status(self, mock_settings):
        """Test database status update helper."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.async_session_factory') as mock_session_factory:
                                with patch('src.services.ingestion.main_processor.DocumentRepository') as mock_doc_repo:
                                    # Setup mocks
                                    mock_session = AsyncMock()
                                    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                                    mock_session_factory.return_value.__aexit__ = AsyncMock()

                                    mock_repo_instance = mock_doc_repo.return_value
                                    mock_repo_instance.update_status = AsyncMock()

                                    processor = MainProcessor()
                                    doc_id = uuid4()

                                    # Update status
                                    await processor._update_db_status(doc_id, ProcessingStatus.PROCESSING)

                                    # Verify
                                    mock_repo_instance.update_status.assert_called_once_with(
                                        doc_id, ProcessingStatus.PROCESSING, None
                                    )

    @pytest.mark.asyncio
    async def test_update_db_status_with_error(self, mock_settings):
        """Test database status update with error message."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.async_session_factory') as mock_session_factory:
                                with patch('src.services.ingestion.main_processor.DocumentRepository') as mock_doc_repo:
                                    # Setup mocks
                                    mock_session = AsyncMock()
                                    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                                    mock_session_factory.return_value.__aexit__ = AsyncMock()

                                    mock_repo_instance = mock_doc_repo.return_value
                                    mock_repo_instance.update_status = AsyncMock()

                                    processor = MainProcessor()
                                    doc_id = uuid4()

                                    # Update status with error
                                    await processor._update_db_status(
                                        doc_id,
                                        ProcessingStatus.FAILED,
                                        "Processing error occurred"
                                    )

                                    # Verify
                                    mock_repo_instance.update_status.assert_called_once_with(
                                        doc_id, ProcessingStatus.FAILED, "Processing error occurred"
                                    )

    @pytest.mark.asyncio
    async def test_update_db_status_none_document_id(self, mock_settings):
        """Test that status update is skipped when document_id is None."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.async_session_factory') as mock_session_factory:
                                processor = MainProcessor()

                                # Should not raise error with None document_id
                                await processor._update_db_status(None, ProcessingStatus.PROCESSING)

                                # Session factory should not be called
                                mock_session_factory.assert_not_called()


class TestMainProcessorValidation:
    """Test document validation in MainProcessor."""

    def test_validate_document_success(self, mock_settings, sample_unified_document):
        """Test successful document validation."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            # Should not raise exception
                            processor._validate_document(sample_unified_document)

    def test_validate_document_empty_chunks(self, mock_settings):
        """Test validation with empty chunks."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            doc = UnifiedDocument(
                                id=uuid4(),
                                title="Empty Doc",
                                source_type=DocumentType.PDF,
                                source_path="test.pdf",
                                content="Test",
                                status=ProcessingStatusEnum.COMPLETED,
                                chunks=[]  # No chunks
                            )

                            # Should not raise, just log warning
                            processor._validate_document(doc)

    def test_validate_document_mismatched_document_id(self, mock_settings):
        """Test validation with mismatched document IDs."""
        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            doc_id = uuid4()
                            wrong_doc_id = uuid4()
                            doc = UnifiedDocument(
                                id=doc_id,
                                title="Test Doc",
                                source_type=DocumentType.PDF,
                                source_path="test.pdf",
                                content="Test",
                                status=ProcessingStatusEnum.COMPLETED,
                                chunks=[
                                    DocumentChunk(
                                        chunk_id=f"{wrong_doc_id}_chunk_0",
                                        document_id=wrong_doc_id,  # Wrong ID
                                        content="Test content",
                                        chunk_index=0
                                    )
                                ]
                            )

                            # Should raise error for mismatched IDs
                            from src.utils.exceptions import DocumentProcessingError
                            with pytest.raises(DocumentProcessingError):
                                processor._validate_document(doc)


class TestMainProcessorChunking:
    """Test chunking functionality in MainProcessor."""

    def test_get_chunking_params_sentence_strategy(self, mock_settings):
        """Test chunking parameters for sentence strategy."""
        mock_settings.rag.chunking_strategy = "sentence"

        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            processor = MainProcessor()

                            params = processor._get_chunking_params()

                            assert params["strategy"] == "sentence"
                            # No embed_model needed for sentence strategy
                            assert params.get("embed_model") is None

    def test_get_chunking_params_semantic_strategy(self, mock_settings):
        """Test chunking parameters for semantic strategy."""
        mock_settings.rag.chunking_strategy = "semantic"

        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.HuggingFaceEmbedding') as mock_hf:
                                mock_hf.return_value = Mock()

                                processor = MainProcessor()
                                params = processor._get_chunking_params()

                                # Should attempt to create embedding model
                                assert params["strategy"] in ["semantic", "sentence"]

    def test_get_chunking_params_semantic_fallback_on_error(self, mock_settings):
        """Test semantic chunking falls back to sentence on error."""
        mock_settings.rag.chunking_strategy = "semantic"

        with patch('src.services.ingestion.main_processor.get_settings', return_value=mock_settings):
            with patch('src.services.ingestion.main_processor.UnstructuredDocumentProcessor'):
                with patch('src.services.ingestion.main_processor.AudioTranscriber'):
                    with patch('src.services.ingestion.main_processor.WebProcessor'):
                        with patch('src.services.ingestion.main_processor.YoutubeProcessor'):
                            with patch('src.services.ingestion.main_processor.HuggingFaceEmbedding') as mock_hf:
                                # Simulate embedding creation failure
                                mock_hf.side_effect = Exception("Model loading failed")

                                processor = MainProcessor()
                                params = processor._get_chunking_params()

                                # Should fall back to sentence strategy
                                assert params["strategy"] == "sentence"
                                assert params.get("embed_model") is None
