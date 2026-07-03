# Contributing Guide

Guidelines for contributing to Granthiq Backend.

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- Docker (optional, for local services)

### Local Setup

```bash
# Clone repository
git clone <repo-url>
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Initialize database
python -m scripts.setup_db

# Run development server
uvicorn src.app:app --reload
```

---

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use `black` for formatting
- Use `ruff` for linting

### Formatting

```bash
# Format code
black src/

# Lint code
ruff check src/
```

---

## Project Structure

```
src/
├── app.py              # FastAPI application
├── config.py           # Settings and configuration
├── db/                 # Database layer
│   ├── models.py       # SQLModel schemas
│   ├── session.py      # Database session
│   └── repositories/   # Repository pattern
├── routers/            # API endpoints
├── services/           # Business logic
├── schemas/            # Pydantic models
└── utils/              # Utilities
```

---

## Making Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring

### Commit Messages

Follow conventional commits:

```
type(scope): description

feat(chat): add streaming response support
fix(documents): handle large file uploads
docs(api): update endpoint documentation
refactor(query): simplify retrieval logic
```

---

## Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific test file
pytest tests/unit/test_chunking.py -v

# Single test
pytest tests/unit/test_chunking.py::test_semantic_chunking -v
```

### Test Structure

```
tests/
├── unit/           # Unit tests
├── integration/    # Integration tests
└── evaluation/     # RAG evaluation tests
```

### Writing Tests

```python
import pytest
from src.services.example import ExampleService

class TestExampleService:
    @pytest.fixture
    def service(self):
        return ExampleService()

    def test_basic_functionality(self, service):
        result = service.do_something()
        assert result is not None

    @pytest.mark.asyncio
    async def test_async_functionality(self, service):
        result = await service.async_method()
        assert result == expected_value
```

---

## Pull Request Process

1. **Create branch** from `main`
2. **Make changes** with clear commits
3. **Write/update tests** for new functionality
4. **Update documentation** if needed
5. **Run tests** locally: `pytest`
6. **Submit PR** with description of changes

### PR Description Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactoring

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
```

---

## Architecture Guidelines

### Adding New Endpoints

1. Create route handler in `src/routers/`
2. Add Pydantic schemas in `src/schemas/`
3. Implement business logic in `src/services/`
4. Register router in `src/routers/router.py`
5. Add tests

### Adding Database Models

1. Define model in `src/db/models.py`
2. Create repository in `src/db/repositories/`
3. Run migration: `alembic revision --autogenerate -m "description"`
4. Apply: `alembic upgrade head`

### Service Layer Pattern

```python
# src/services/example/service.py
from loguru import logger

class ExampleService:
    def __init__(self, repository: ExampleRepository):
        self.repository = repository

    async def process(self, data: dict) -> Result:
        # Business logic here
        logger.info(f"Processing: {data}")
        return await self.repository.save(data)
```

---

## Security

- Never commit secrets or credentials
- Use environment variables for configuration
- Validate all user inputs
- Follow OWASP guidelines
- Report security issues privately

---

## Questions?

Open an issue for questions or suggestions.
