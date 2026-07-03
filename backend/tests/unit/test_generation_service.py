"""
Unit tests for GenerationService

Tests the content generation functionality including:
- Podcast generation
- Quiz generation
- Flashcard generation
- Mindmap generation
- Error handling
- Database record creation and updates
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID
from datetime import datetime, timezone

from src.services.generation.service import GenerationService
from src.db.models import ContentType, ProcessingStatus, Notebook, Document
from src.schemas.content import PodcastScript, Quiz, FlashcardDeck, MindMap, DialogueTurn, QuizQuestion, Flashcard, MindMapNode


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.rag = Mock()
    settings.rag.chunk_size = 1000
    settings.rag.chunk_overlap = 200
    settings.rag.top_k_results = 20
    settings.rag.chunking_strategy = "semantic"
    settings.llm = Mock()
    settings.llm.provider = "gemini"
    settings.llm.model_name = "gemini-2.5-flash"
    settings.llm.temperature = 0.7
    settings.llm.groq_api_key = None
    settings.llm.gemini_api_key = "test-key"
    settings.llm.openai_api_key = None
    settings.embedding = Mock()
    settings.embedding.model = "all-MiniLM-L6-v2"
    settings.anonymous_user_id = uuid4()
    settings.evaluation = Mock()
    settings.evaluation.enabled = False
    return settings


@pytest.fixture
def mock_session():
    """Mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def sample_notebook():
    """Sample notebook for testing."""
    return Notebook(
        id=uuid4(),
        user_id=uuid4(),
        title="Test Notebook",
        settings={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_documents():
    """Sample documents for testing."""
    notebook_id = uuid4()
    return [
        Document(
            id=uuid4(),
            notebook_id=notebook_id,
            filename="doc1.pdf",
            file_path="path/to/doc1.pdf",
            mime_type="application/pdf",
            status=ProcessingStatus.COMPLETED,
            chunk_count=10,
            created_at=datetime.now(timezone.utc)
        ),
        Document(
            id=uuid4(),
            notebook_id=notebook_id,
            filename="doc2.pdf",
            file_path="path/to/doc2.pdf",
            mime_type="application/pdf",
            status=ProcessingStatus.COMPLETED,
            chunk_count=15,
            created_at=datetime.now(timezone.utc)
        )
    ]


@pytest.fixture
def sample_podcast_script():
    """Sample podcast script for testing."""
    return PodcastScript(
        title="Test Podcast",
        description="A test podcast about AI",
        dialogue=[
            DialogueTurn(speaker="Host", text="Welcome to our podcast!"),
            DialogueTurn(speaker="Expert", text="Thank you for having me."),
            DialogueTurn(speaker="Host", text="Let's discuss AI today."),
        ],
        duration_estimate="5 minutes",
        audio_url=None
    )


@pytest.fixture
def sample_quiz():
    """Sample quiz for testing."""
    return Quiz(
        title="Test Quiz",
        description="A quiz about AI concepts",
        questions=[
            QuizQuestion(
                question="What does AI stand for?",
                options=["Artificial Intelligence", "Automated Interface", "Advanced Input", "Analog Integration"],
                correct_answer="Artificial Intelligence",
                explanation="AI stands for Artificial Intelligence"
            ),
            QuizQuestion(
                question="What is machine learning?",
                options=["A type of AI", "A programming language", "A database", "A network protocol"],
                correct_answer="A type of AI",
                explanation="Machine learning is a subset of AI"
            )
        ],
        difficulty="medium"
    )


@pytest.fixture
def sample_flashcard_deck():
    """Sample flashcard deck for testing."""
    return FlashcardDeck(
        title="AI Flashcards",
        description="Flashcards about AI concepts",
        cards=[
            Flashcard(front="What is AI?", back="Artificial Intelligence"),
            Flashcard(front="What is ML?", back="Machine Learning"),
            Flashcard(front="What is NLP?", back="Natural Language Processing"),
        ],
        category="Technology"
    )


@pytest.fixture
def sample_mindmap():
    """Sample mindmap for testing."""
    return MindMap(
        title="AI Concepts",
        central_topic="Artificial Intelligence",
        nodes=[
            MindMapNode(
                id="1",
                label="Machine Learning",
                parent_id=None,
                children=["2", "3"]
            ),
            MindMapNode(
                id="2",
                label="Supervised Learning",
                parent_id="1",
                children=[]
            ),
            MindMapNode(
                id="3",
                label="Unsupervised Learning",
                parent_id="1",
                children=[]
            )
        ]
    )


class TestGenerationService:
    """Test suite for GenerationService."""

    @pytest.mark.asyncio
    async def test_generate_podcast(
        self,
        mock_settings,
        mock_session,
        sample_notebook,
        sample_documents,
        sample_podcast_script
    ):
        """Test podcast generation."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                with patch('src.services.generation.service.PodcastGenerator') as mock_podcast_gen:
                                    with patch('src.services.generation.service.AudioGenerator') as mock_audio_gen:
                                        # Setup mocks
                                        mock_engine = Mock()
                                        mock_response = Mock()
                                        mock_response.response = "Test context about AI and technology."
                                        mock_engine.aquery = AsyncMock(return_value=mock_response)
                                        mock_builder_instance = Mock()
                                        mock_builder_instance.with_llm.return_value = mock_builder_instance
                                        mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                        mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                        mock_builder_instance.build.return_value = mock_engine
                                        mock_builder.return_value = mock_builder_instance

                                        # Mock repositories
                                        mock_content_repo = mock_content_repo_class.return_value
                                        mock_doc_repo = mock_doc_repo_class.return_value
                                        mock_notebook_repo = mock_notebook_repo_class.return_value

                                        mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)
                                        mock_doc_repo.get_by_notebook = AsyncMock(return_value=sample_documents)

                                        mock_content_record = Mock()
                                        mock_content_record.id = uuid4()
                                        mock_content_repo.create_content = AsyncMock(return_value=mock_content_record)
                                        mock_content_repo.update_content = AsyncMock()

                                        # Mock podcast generator
                                        mock_podcast_gen_instance = mock_podcast_gen.return_value
                                        mock_podcast_gen_instance.generate = AsyncMock(return_value=sample_podcast_script)

                                        # Mock audio generator
                                        mock_audio_gen_instance = mock_audio_gen.return_value
                                        mock_audio_gen_instance.generate_podcast_audio = AsyncMock(return_value="https://storage.example.com/podcast.mp3")

                                        # Create service and generate
                                        service = GenerationService()
                                        result = await service.generate_content(
                                            session=mock_session,
                                            content_type="podcast",
                                            notebook_id=sample_notebook.id,
                                            user_id=sample_notebook.user_id
                                        )

                                        # Verify
                                        assert result is not None
                                        mock_content_repo.create_content.assert_called_once()
                                        mock_podcast_gen_instance.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_quiz(
        self,
        mock_settings,
        mock_session,
        sample_notebook,
        sample_documents,
        sample_quiz
    ):
        """Test quiz generation."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                with patch('src.services.generation.service.QuizGenerator') as mock_quiz_gen:
                                    # Setup mocks
                                    mock_engine = Mock()
                                    mock_response = Mock()
                                    mock_response.response = "Test context about AI and technology."
                                    mock_engine.aquery = AsyncMock(return_value=mock_response)
                                    mock_builder_instance = Mock()
                                    mock_builder_instance.with_llm.return_value = mock_builder_instance
                                    mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                    mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                    mock_builder_instance.build.return_value = mock_engine
                                    mock_builder.return_value = mock_builder_instance

                                    # Mock repositories
                                    mock_content_repo = mock_content_repo_class.return_value
                                    mock_doc_repo = mock_doc_repo_class.return_value
                                    mock_notebook_repo = mock_notebook_repo_class.return_value

                                    mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)
                                    mock_doc_repo.get_by_notebook = AsyncMock(return_value=sample_documents)

                                    mock_content_record = Mock()
                                    mock_content_record.id = uuid4()
                                    mock_content_repo.create_content = AsyncMock(return_value=mock_content_record)
                                    mock_content_repo.update_content = AsyncMock()

                                    # Mock quiz generator
                                    mock_quiz_gen_instance = mock_quiz_gen.return_value
                                    mock_quiz_gen_instance.generate = AsyncMock(return_value=sample_quiz)

                                    # Create service and generate
                                    service = GenerationService()
                                    result = await service.generate_content(
                                        session=mock_session,
                                        content_type="quiz",
                                        notebook_id=sample_notebook.id,
                                        user_id=sample_notebook.user_id
                                    )

                                    # Verify
                                    assert result is not None
                                    mock_quiz_gen_instance.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_flashcard(
        self,
        mock_settings,
        mock_session,
        sample_notebook,
        sample_documents,
        sample_flashcard_deck
    ):
        """Test flashcard generation."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                with patch('src.services.generation.service.FlashcardGenerator') as mock_flashcard_gen:
                                    # Setup mocks
                                    mock_engine = Mock()
                                    mock_response = Mock()
                                    mock_response.response = "Test context about AI and technology."
                                    mock_engine.aquery = AsyncMock(return_value=mock_response)
                                    mock_builder_instance = Mock()
                                    mock_builder_instance.with_llm.return_value = mock_builder_instance
                                    mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                    mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                    mock_builder_instance.build.return_value = mock_engine
                                    mock_builder.return_value = mock_builder_instance

                                    # Mock repositories
                                    mock_content_repo = mock_content_repo_class.return_value
                                    mock_doc_repo = mock_doc_repo_class.return_value
                                    mock_notebook_repo = mock_notebook_repo_class.return_value

                                    mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)
                                    mock_doc_repo.get_by_notebook = AsyncMock(return_value=sample_documents)

                                    mock_content_record = Mock()
                                    mock_content_record.id = uuid4()
                                    mock_content_repo.create_content = AsyncMock(return_value=mock_content_record)
                                    mock_content_repo.update_content = AsyncMock()

                                    # Mock flashcard generator
                                    mock_flashcard_gen_instance = mock_flashcard_gen.return_value
                                    mock_flashcard_gen_instance.generate = AsyncMock(return_value=sample_flashcard_deck)

                                    # Create service and generate
                                    service = GenerationService()
                                    result = await service.generate_content(
                                        session=mock_session,
                                        content_type="flashcard",
                                        notebook_id=sample_notebook.id,
                                        user_id=sample_notebook.user_id
                                    )

                                    # Verify
                                    assert result is not None
                                    mock_flashcard_gen_instance.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_mindmap(
        self,
        mock_settings,
        mock_session,
        sample_notebook,
        sample_documents,
        sample_mindmap
    ):
        """Test mindmap generation."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                with patch('src.services.generation.service.MindMapGenerator') as mock_mindmap_gen:
                                    # Setup mocks
                                    mock_engine = Mock()
                                    mock_response = Mock()
                                    mock_response.response = "Test context about AI and technology."
                                    mock_engine.aquery = AsyncMock(return_value=mock_response)
                                    mock_builder_instance = Mock()
                                    mock_builder_instance.with_llm.return_value = mock_builder_instance
                                    mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                    mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                    mock_builder_instance.build.return_value = mock_engine
                                    mock_builder.return_value = mock_builder_instance

                                    # Mock repositories
                                    mock_content_repo = mock_content_repo_class.return_value
                                    mock_doc_repo = mock_doc_repo_class.return_value
                                    mock_notebook_repo = mock_notebook_repo_class.return_value

                                    mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)
                                    mock_doc_repo.get_by_notebook = AsyncMock(return_value=sample_documents)

                                    mock_content_record = Mock()
                                    mock_content_record.id = uuid4()
                                    mock_content_repo.create_content = AsyncMock(return_value=mock_content_record)
                                    mock_content_repo.update_content = AsyncMock()

                                    # Mock mindmap generator
                                    mock_mindmap_gen_instance = mock_mindmap_gen.return_value
                                    mock_mindmap_gen_instance.generate = AsyncMock(return_value=sample_mindmap)

                                    # Create service and generate
                                    service = GenerationService()
                                    result = await service.generate_content(
                                        session=mock_session,
                                        content_type="mindmap",
                                        notebook_id=sample_notebook.id,
                                        user_id=sample_notebook.user_id
                                    )

                                    # Verify
                                    assert result is not None
                                    mock_mindmap_gen_instance.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_no_documents_returns_none(
        self,
        mock_settings,
        mock_session,
        sample_notebook
    ):
        """Test that generation returns None when no documents exist."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                # Setup mocks
                                mock_engine = Mock()
                                mock_builder_instance = Mock()
                                mock_builder_instance.with_llm.return_value = mock_builder_instance
                                mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                mock_builder_instance.build.return_value = mock_engine
                                mock_builder.return_value = mock_builder_instance

                                # Mock repositories
                                mock_doc_repo = mock_doc_repo_class.return_value
                                mock_notebook_repo = mock_notebook_repo_class.return_value

                                mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)
                                mock_doc_repo.get_by_notebook = AsyncMock(return_value=[])  # No documents

                                # Create service and generate
                                service = GenerationService()
                                result = await service.generate_content(
                                    session=mock_session,
                                    content_type="quiz",
                                    notebook_id=sample_notebook.id,
                                    user_id=sample_notebook.user_id
                                )

                                # Should return None when no documents
                                assert result is None

    @pytest.mark.asyncio
    async def test_generate_with_nonexistent_notebook_returns_none(
        self,
        mock_settings,
        mock_session
    ):
        """Test that generation returns None when notebook doesn't exist."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                # Setup mocks
                                mock_engine = Mock()
                                mock_builder_instance = Mock()
                                mock_builder_instance.with_llm.return_value = mock_builder_instance
                                mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                mock_builder_instance.build.return_value = mock_engine
                                mock_builder.return_value = mock_builder_instance

                                # Mock notebook not found
                                mock_notebook_repo = mock_notebook_repo_class.return_value
                                mock_notebook_repo.get_notebook = AsyncMock(return_value=None)

                                # Create service and generate
                                service = GenerationService()
                                result = await service.generate_content(
                                    session=mock_session,
                                    content_type="quiz",
                                    notebook_id=uuid4(),
                                    user_id=uuid4()
                                )

                                # Should return None when notebook not found
                                assert result is None

    @pytest.mark.asyncio
    async def test_generate_with_insufficient_context_returns_none(
        self,
        mock_settings,
        mock_session,
        sample_notebook,
        sample_documents
    ):
        """Test that generation returns None when context is insufficient."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                # Setup mocks
                                mock_engine = Mock()
                                mock_response = Mock()
                                # Simulate policy refusal
                                mock_response.response = "I'm sorry, I don't have enough information."
                                mock_engine.aquery = AsyncMock(return_value=mock_response)
                                mock_builder_instance = Mock()
                                mock_builder_instance.with_llm.return_value = mock_builder_instance
                                mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                mock_builder_instance.build.return_value = mock_engine
                                mock_builder.return_value = mock_builder_instance

                                # Mock repositories
                                mock_doc_repo = mock_doc_repo_class.return_value
                                mock_notebook_repo = mock_notebook_repo_class.return_value

                                mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)
                                mock_doc_repo.get_by_notebook = AsyncMock(return_value=sample_documents)

                                # Create service and generate
                                service = GenerationService()
                                result = await service.generate_content(
                                    session=mock_session,
                                    content_type="quiz",
                                    notebook_id=sample_notebook.id,
                                    user_id=sample_notebook.user_id
                                )

                                # Should return None when context is insufficient
                                assert result is None

    @pytest.mark.asyncio
    async def test_generate_with_specific_document_ids(
        self,
        mock_settings,
        mock_session,
        sample_notebook,
        sample_documents,
        sample_quiz
    ):
        """Test generation with specific document IDs filter."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                with patch('src.services.generation.service.QuizGenerator') as mock_quiz_gen:
                                    # Setup mocks
                                    mock_engine = Mock()
                                    mock_response = Mock()
                                    mock_response.response = "Test context about AI."
                                    mock_engine.aquery = AsyncMock(return_value=mock_response)
                                    mock_builder_instance = Mock()
                                    mock_builder_instance.with_llm.return_value = mock_builder_instance
                                    mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                    mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                    mock_builder_instance.build.return_value = mock_engine
                                    mock_builder.return_value = mock_builder_instance

                                    # Mock repositories
                                    mock_content_repo = mock_content_repo_class.return_value
                                    mock_notebook_repo = mock_notebook_repo_class.return_value

                                    mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)

                                    mock_content_record = Mock()
                                    mock_content_record.id = uuid4()
                                    mock_content_repo.create_content = AsyncMock(return_value=mock_content_record)
                                    mock_content_repo.update_content = AsyncMock()

                                    # Mock quiz generator
                                    mock_quiz_gen_instance = mock_quiz_gen.return_value
                                    mock_quiz_gen_instance.generate = AsyncMock(return_value=sample_quiz)

                                    # Create service and generate with specific document IDs
                                    service = GenerationService()
                                    specific_doc_ids = [sample_documents[0].id]
                                    result = await service.generate_content(
                                        session=mock_session,
                                        content_type="quiz",
                                        notebook_id=sample_notebook.id,
                                        document_ids=specific_doc_ids,
                                        user_id=sample_notebook.user_id
                                    )

                                    # Verify generation was called
                                    assert result is not None
                                    mock_quiz_gen_instance.generate.assert_called_once()


class TestGenerationServiceErrorHandling:
    """Test error handling in GenerationService."""

    @pytest.mark.asyncio
    async def test_generation_error_updates_status_to_failed(
        self,
        mock_settings,
        mock_session,
        sample_notebook,
        sample_documents
    ):
        """Test that errors during generation update content status to FAILED."""
        with patch('src.services.generation.service.get_settings', return_value=mock_settings):
            with patch('src.services.generation.service.QueryEngineBuilder') as mock_builder:
                with patch('src.services.generation.service.create_llamaindex_llm') as mock_llm:
                    with patch('src.services.generation.service.ContentRepository') as mock_content_repo_class:
                        with patch('src.services.generation.service.DocumentRepository') as mock_doc_repo_class:
                            with patch('src.services.generation.service.NotebookRepository') as mock_notebook_repo_class:
                                with patch('src.services.generation.service.QuizGenerator') as mock_quiz_gen:
                                    # Setup mocks
                                    mock_engine = Mock()
                                    mock_response = Mock()
                                    mock_response.response = "Test context"
                                    mock_engine.aquery = AsyncMock(return_value=mock_response)
                                    mock_builder_instance = Mock()
                                    mock_builder_instance.with_llm.return_value = mock_builder_instance
                                    mock_builder_instance.with_retriever.return_value = mock_builder_instance
                                    mock_builder_instance.with_synthesizer.return_value = mock_builder_instance
                                    mock_builder_instance.build.return_value = mock_engine
                                    mock_builder.return_value = mock_builder_instance

                                    # Mock repositories
                                    mock_content_repo = mock_content_repo_class.return_value
                                    mock_doc_repo = mock_doc_repo_class.return_value
                                    mock_notebook_repo = mock_notebook_repo_class.return_value

                                    mock_notebook_repo.get_notebook = AsyncMock(return_value=sample_notebook)
                                    mock_doc_repo.get_by_notebook = AsyncMock(return_value=sample_documents)

                                    mock_content_record = Mock()
                                    mock_content_record.id = uuid4()
                                    mock_content_repo.create_content = AsyncMock(return_value=mock_content_record)
                                    mock_content_repo.update_content = AsyncMock()

                                    # Mock generator to raise error
                                    mock_quiz_gen_instance = mock_quiz_gen.return_value
                                    mock_quiz_gen_instance.generate = AsyncMock(side_effect=Exception("LLM API error"))

                                    # Create service and generate
                                    service = GenerationService()
                                    result = await service.generate_content(
                                        session=mock_session,
                                        content_type="quiz",
                                        notebook_id=sample_notebook.id,
                                        user_id=sample_notebook.user_id
                                    )

                                    # Should return None on error
                                    assert result is None

                                    # Verify status was updated to FAILED
                                    update_calls = mock_content_repo.update_content.call_args_list
                                    assert len(update_calls) > 0
                                    # Check last call was with FAILED status
                                    last_call = update_calls[-1]
                                    assert last_call.kwargs.get('status') == ProcessingStatus.FAILED
