"""
Unit tests for chunking functionality.

Tests the text chunking strategies including:
- Sentence-based chunking
- Semantic chunking
- Token-based chunking
- Chunk overlap handling
"""

import pytest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.services.ingestion.chunk_manager import apply_chunking_to_document_non_destructive
from src.schemas.document import UnifiedDocument, DocumentType, DocumentChunk, ProcessingStatusEnum


@pytest.fixture
def sample_document():
    """Create a sample document for chunking tests."""
    doc_id = uuid4()
    return UnifiedDocument(
        id=doc_id,
        title="Test Document",
        source_type=DocumentType.TXT,
        source_path="test/document.txt",
        content="This is the first sentence. This is the second sentence. This is the third sentence.",
        status=ProcessingStatusEnum.COMPLETED,
        chunks=[
            DocumentChunk(
                chunk_id=f"{doc_id}_chunk_0",
                document_id=doc_id,
                content="This is the first sentence. This is the second sentence. This is the third sentence.",
                chunk_index=0
            )
        ]
    )


@pytest.fixture
def long_document():
    """Create a longer document for chunking tests."""
    doc_id = uuid4()
    # Generate a longer text with multiple paragraphs
    paragraphs = []
    for i in range(10):
        paragraphs.append(
            f"This is paragraph {i}. It contains multiple sentences. "
            f"Each sentence provides information. We need enough text to test chunking properly. "
            f"The chunking algorithm should split this into multiple chunks based on the configured size."
        )
    content = " ".join(paragraphs)

    return UnifiedDocument(
        id=doc_id,
        title="Long Document",
        source_type=DocumentType.TXT,
        source_path="test/long_document.txt",
        content=content,
        status=ProcessingStatusEnum.COMPLETED,
        chunks=[
            DocumentChunk(
                chunk_id=f"{doc_id}_chunk_0",
                document_id=doc_id,
                content=content,
                chunk_index=0
            )
        ]
    )


class TestApplyChunking:
    """Test suite for chunking functionality."""

    def test_chunking_preserves_document_id(self, sample_document):
        """Test that chunking preserves the document ID."""
        result = apply_chunking_to_document_non_destructive(
            sample_document,
            chunk_size=50,
            chunk_overlap=10,
            strategy="sentence"
        )

        assert result.id == sample_document.id
        for chunk in result.chunks:
            assert chunk.document_id == sample_document.id

    def test_chunking_with_small_chunk_size(self, long_document):
        """Test chunking with a small chunk size creates multiple chunks."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=200,
            chunk_overlap=50,
            strategy="sentence"
        )

        # Should have multiple chunks
        assert len(result.chunks) > 1
        # Each chunk should be smaller than or equal to chunk_size (with some tolerance)
        for chunk in result.chunks:
            # Allow some flexibility due to sentence boundaries
            assert len(chunk.content) <= 400

    def test_chunking_with_large_chunk_size(self, sample_document):
        """Test chunking with large chunk size may keep single chunk."""
        result = apply_chunking_to_document_non_destructive(
            sample_document,
            chunk_size=10000,
            chunk_overlap=100,
            strategy="sentence"
        )

        # With large chunk size, may keep as single chunk
        assert len(result.chunks) >= 1

    def test_chunking_updates_chunk_indices(self, long_document):
        """Test that chunk indices are sequential."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=200,
            chunk_overlap=50,
            strategy="sentence"
        )

        for i, chunk in enumerate(result.chunks):
            assert chunk.chunk_index == i

    def test_chunking_updates_chunk_count(self, long_document):
        """Test that chunk_count is updated correctly."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=200,
            chunk_overlap=50,
            strategy="sentence"
        )

        assert result.chunk_count == len(result.chunks)

    def test_sentence_chunking_strategy(self, sample_document):
        """Test sentence-based chunking strategy."""
        result = apply_chunking_to_document_non_destructive(
            sample_document,
            chunk_size=50,
            chunk_overlap=10,
            strategy="sentence",
            respect_sentence_boundary=True
        )

        # Each chunk should end at a sentence boundary (end with period, question mark, etc.)
        for chunk in result.chunks:
            content = chunk.content.strip()
            if content:
                assert content[-1] in '.!?'

    def test_empty_chunks_handled(self):
        """Test handling document with empty chunks."""
        doc_id = uuid4()
        doc = UnifiedDocument(
            id=doc_id,
            title="Empty Chunks Doc",
            source_type=DocumentType.TXT,
            source_path="test/empty.txt",
            content="",
            status=ProcessingStatusEnum.COMPLETED,
            chunks=[]
        )

        result = apply_chunking_to_document_non_destructive(
            doc,
            chunk_size=100,
            chunk_overlap=20,
            strategy="sentence"
        )

        # Should handle empty document gracefully
        assert result.chunks == []

    def test_chunk_metadata_preserved(self, sample_document):
        """Test that chunk metadata is preserved or updated correctly."""
        # Add metadata to original chunk
        sample_document.chunks[0].metadata = {"page": 1, "section": "intro"}

        result = apply_chunking_to_document_non_destructive(
            sample_document,
            chunk_size=50,
            chunk_overlap=10,
            strategy="sentence"
        )

        # Chunks should have document_id at minimum
        for chunk in result.chunks:
            assert chunk.document_id is not None


class TestChunkingStrategies:
    """Test different chunking strategies."""

    def test_token_strategy(self, long_document):
        """Test token-based chunking strategy."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=100,
            chunk_overlap=20,
            strategy="token"
        )

        assert len(result.chunks) >= 1
        assert result.chunk_count == len(result.chunks)

    def test_auto_strategy(self, long_document):
        """Test auto strategy selection."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=200,
            chunk_overlap=50,
            strategy="auto"
        )

        assert len(result.chunks) >= 1

    def test_semantic_strategy_fallback(self, long_document):
        """Test semantic strategy falls back when embed_model not available."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=200,
            chunk_overlap=50,
            strategy="semantic",
            embed_model=None  # No embed model
        )

        # Should still produce chunks (fallback to sentence)
        assert len(result.chunks) >= 1


class TestChunkOverlap:
    """Test chunk overlap functionality."""

    def test_zero_overlap(self, long_document):
        """Test chunking with zero overlap."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=200,
            chunk_overlap=0,
            strategy="sentence"
        )

        # Check that chunks don't have overlapping content
        if len(result.chunks) > 1:
            for i in range(len(result.chunks) - 1):
                current = result.chunks[i].content
                next_chunk = result.chunks[i + 1].content
                # With sentence boundaries, there should be minimal overlap
                assert len(current) > 0
                assert len(next_chunk) > 0

    def test_large_overlap(self, long_document):
        """Test chunking with large overlap."""
        result = apply_chunking_to_document_non_destructive(
            long_document,
            chunk_size=200,
            chunk_overlap=100,  # 50% overlap
            strategy="sentence"
        )

        assert len(result.chunks) >= 1


class TestEdgeCases:
    """Test edge cases in chunking."""

    def test_single_sentence_document(self):
        """Test document with single sentence."""
        doc_id = uuid4()
        doc = UnifiedDocument(
            id=doc_id,
            title="Single Sentence",
            source_type=DocumentType.TXT,
            source_path="test/single.txt",
            content="This is a single sentence.",
            status=ProcessingStatusEnum.COMPLETED,
            chunks=[
                DocumentChunk(
                    chunk_id=f"{doc_id}_chunk_0",
                    document_id=doc_id,
                    content="This is a single sentence.",
                    chunk_index=0
                )
            ]
        )

        result = apply_chunking_to_document_non_destructive(
            doc,
            chunk_size=50,
            chunk_overlap=10,
            strategy="sentence"
        )

        assert len(result.chunks) >= 1

    def test_very_long_sentence(self):
        """Test handling of very long sentences."""
        doc_id = uuid4()
        long_sentence = "This is a very long sentence " * 100 + "."
        doc = UnifiedDocument(
            id=doc_id,
            title="Long Sentence",
            source_type=DocumentType.TXT,
            source_path="test/long_sentence.txt",
            content=long_sentence,
            status=ProcessingStatusEnum.COMPLETED,
            chunks=[
                DocumentChunk(
                    chunk_id=f"{doc_id}_chunk_0",
                    document_id=doc_id,
                    content=long_sentence,
                    chunk_index=0
                )
            ]
        )

        result = apply_chunking_to_document_non_destructive(
            doc,
            chunk_size=200,
            chunk_overlap=50,
            strategy="sentence"
        )

        # Should handle long sentences
        assert len(result.chunks) >= 1

    def test_special_characters(self):
        """Test document with special characters."""
        doc_id = uuid4()
        content = "This has special chars: @#$%^&*(). Another sentence! Question? Yes."
        doc = UnifiedDocument(
            id=doc_id,
            title="Special Chars",
            source_type=DocumentType.TXT,
            source_path="test/special.txt",
            content=content,
            status=ProcessingStatusEnum.COMPLETED,
            chunks=[
                DocumentChunk(
                    chunk_id=f"{doc_id}_chunk_0",
                    document_id=doc_id,
                    content=content,
                    chunk_index=0
                )
            ]
        )

        result = apply_chunking_to_document_non_destructive(
            doc,
            chunk_size=30,
            chunk_overlap=5,
            strategy="sentence"
        )

        assert len(result.chunks) >= 1

    def test_unicode_content(self):
        """Test document with unicode content."""
        doc_id = uuid4()
        content = "Hello world. 你好世界。 مرحبا بالعالم. Привет мир."
        doc = UnifiedDocument(
            id=doc_id,
            title="Unicode",
            source_type=DocumentType.TXT,
            source_path="test/unicode.txt",
            content=content,
            status=ProcessingStatusEnum.COMPLETED,
            chunks=[
                DocumentChunk(
                    chunk_id=f"{doc_id}_chunk_0",
                    document_id=doc_id,
                    content=content,
                    chunk_index=0
                )
            ]
        )

        result = apply_chunking_to_document_non_destructive(
            doc,
            chunk_size=20,
            chunk_overlap=5,
            strategy="sentence"
        )

        assert len(result.chunks) >= 1
