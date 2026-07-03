"""
Shared pytest fixtures for API integration tests.
"""
import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import uuid
import jwt
import time
import io
from datetime import datetime, timezone

# Helper function for timezone-aware UTC datetime (matches model definition)
def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)
from typing import AsyncGenerator
from pytest import fixture
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from src.app import create_app
from src.services.auth import get_current_user
from src.db.session import get_session, async_session_factory
from src.config import get_settings
from src.db.models import User, Notebook, Document, ProcessingStatus
from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.document import DocumentRepository
from src.services.observability.langfuse_config import setup_langfuse, flush_langfuse, get_langfuse_status
from sqlmodel import select
from sqlalchemy.exc import IntegrityError

# Initialize observability for tests
logger.info("Initializing observability for tests...")
langfuse_status = get_langfuse_status()
if langfuse_status.get("enabled") and langfuse_status.get("initialized"):
    logger.info("✅ Langfuse observability enabled and initialized")
else:
    logger.warning("⚠️ Langfuse observability not enabled or not initialized")

# Fixed test user ID (reused across all tests)
# Using a fixed UUID that exists in the database - do not recreate/delete users
# Can be overridden via environment variable for different test environments
import os
_TEST_USER_ID_STR = os.getenv("TEST_USER_ID", "eaa585c2-9a2c-445e-9b8c-eaf5bb6bf4fa")
TEST_USER_ID = uuid.UUID(_TEST_USER_ID_STR)
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "test@notebookllm.test")

# Second user ID for testing unauthorized access
OTHER_USER_ID = uuid.uuid4()
OTHER_USER_EMAIL = "other@notebookllm.test"


@fixture(scope="session")
def test_user_id():
    """Fixed test user ID for all tests."""
    return TEST_USER_ID


@fixture(scope="session")
def test_user_email():
    """Fixed test user email for all tests."""
    return TEST_USER_EMAIL


@fixture(scope="session")
def other_user_id():
    """Another user ID for testing unauthorized access."""
    return OTHER_USER_ID


@fixture(scope="session")
def test_jwt_token():
    """Generate JWT token for test user using SUPABASE_JWT_SECRET."""
    settings = get_settings()
    if not settings.auth.secret_key:
        raise ValueError("SUPABASE_JWT_SECRET must be set in environment")
    
    payload = {
        "aud": "authenticated",
        "role": "authenticated",
        "sub": str(TEST_USER_ID),
        "email": TEST_USER_EMAIL,
        "exp": int(time.time()) + (60 * 60 * 24 * 30)  # 30 days
    }
    return jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.algorithm)


@fixture(scope="session")
def expired_jwt_token():
    """Generate expired JWT token for testing."""
    settings = get_settings()
    if not settings.auth.secret_key:
        raise ValueError("SUPABASE_JWT_SECRET must be set in environment")
    
    payload = {
        "aud": "authenticated",
        "role": "authenticated",
        "sub": str(TEST_USER_ID),
        "email": TEST_USER_EMAIL,
        "exp": int(time.time()) - 3600  # Expired 1 hour ago
    }
    return jwt.encode(payload, settings.auth.secret_key, algorithm=settings.auth.algorithm)


@fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for each test."""
    async with async_session_factory() as session:
        yield session
        # Cleanup: rollback any uncommitted changes
        await session.rollback()


@fixture(scope="function")
async def app(db_session):
    """Create FastAPI app with auth and session overrides."""
    app = create_app()
    
    # Override get_current_user to return test_user_id
    # The actual dependency has: credentials, settings, session
    # But we'll override it to just return the test user ID
    from fastapi.security import HTTPAuthorizationCredentials
    from src.config import Settings
    
    async def override_get_current_user(
        credentials: HTTPAuthorizationCredentials = None,
        settings: Settings = None,
        session: AsyncSession = None
    ) -> uuid.UUID:
        return TEST_USER_ID
    
    # Override get_session to use our test session
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_session] = override_get_session
    
    yield app
    
    # Cleanup
    app.dependency_overrides.clear()


@fixture(scope="function")
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing."""
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        # Flush observability events after each test
        try:
            flush_langfuse()
        except Exception as e:
            logger.debug(f"Failed to flush Langfuse events: {e}")


async def ensure_test_user_exists(session: AsyncSession) -> User:
    """
    Helper function to ensure test user exists in database.
    Can be used in main functions and fixtures.
    
    NOTE: Does NOT delete/recreate users - just checks if they exist.
    The user ID is fixed and should already exist in the database.
    """
    # First, check if user with TEST_USER_ID exists
    user = await session.get(User, TEST_USER_ID)
    if user:
        logger.debug(f"✅ Test user exists with ID {TEST_USER_ID}")
        return user
    
    # User doesn't exist - create it (but don't delete existing users with same email)
    logger.debug(f"⚠️ Test user with ID {TEST_USER_ID} not found. Creating new user.")
    try:
        user = User(
            id=TEST_USER_ID,
            email=TEST_USER_EMAIL,
            hashed_password="MANAGED_BY_SUPABASE",
            is_active=True,
            created_at=utc_now()  # Use timezone-aware UTC datetime
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.debug(f"✅ Created test user with ID {TEST_USER_ID}")
    except IntegrityError:
        # Handle race condition: user might have been created concurrently
        await session.rollback()
        # Try to get the user again
        user = await session.get(User, TEST_USER_ID)
        if not user:
            # If still not found, try by email
            statement = select(User).where(User.email == TEST_USER_EMAIL)
            result = await session.exec(statement)
            user = result.first()
        if not user:
            raise
    
    return user


@fixture(scope="function")
async def test_user(db_session: AsyncSession, test_user_id, test_user_email):
    """Ensure test user exists in database."""
    user = await db_session.get(User, test_user_id)
    if not user:
        user = User(
            id=test_user_id,
            email=test_user_email,
            hashed_password="MANAGED_BY_SUPABASE",
            is_active=True,
            created_at=utc_now()  # Use timezone-aware UTC datetime
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@fixture(scope="function")
async def test_notebook(db_session: AsyncSession, test_user) -> Notebook:
    """Create a test notebook for the test user."""
    repo = NotebookRepository(db_session)
    notebook = await repo.create_notebook(test_user.id, "Test Notebook")
    return notebook


@fixture(scope="function")
async def test_document(db_session: AsyncSession, test_notebook) -> Document:
    """Create a test document in the test notebook."""
    repo = DocumentRepository(db_session)
    doc = Document(
        notebook_id=test_notebook.id,
        filename="test.pdf",
        file_path=f"notebooks/{test_notebook.user_id}/{test_notebook.id}/test.pdf",
        mime_type="application/pdf",
        status=ProcessingStatus.COMPLETED,
        chunk_count=5
    )
    saved_doc = await repo.create(doc)
    return saved_doc


@fixture
def sample_pdf_content():
    """Generate sample PDF content for testing."""
    from tests.fixtures.test_data import create_sample_pdf
    return create_sample_pdf()


@fixture
def sample_text_content():
    """Load actual notes.txt from uploads folder for testing."""
    from pathlib import Path
    txt_path = Path(__file__).parent.parent.parent / "data" / "uploads" / "notes.txt"
    if txt_path.exists():
        with open(txt_path, "rb") as f:
            return f.read()
    else:
        # Fallback to simple text if file not found
        return b"This is a test document with some content for testing purposes."
