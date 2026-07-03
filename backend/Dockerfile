# ============================================================================
# FAST Multi-Stage Dockerfile - Optimized for Quick Builds
# ============================================================================
#
# DEFAULT MODE (Combined API + Worker):
#   The API server runs with an embedded Procrastinate worker.
#   This is cost-effective for Railway/Render ($5 plans).
#   Set ENABLE_EMBEDDED_WORKER=true (default) to use this mode.
#
# SEPARATE WORKER MODE (for scaling):
#   Deploy two services:
#   1. API: Use default target (runtime)
#   2. Worker: Use target "worker" with ENABLE_EMBEDDED_WORKER=false on API
#
# ============================================================================

FROM python:3.11.8-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# =============================================================================
# SYSTEM DEPENDENCIES FOR UNSTRUCTURED LIBRARY
# =============================================================================
# Unstructured requires these system packages for document processing:
# - libmagic-dev: File type detection (python-magic)
# - poppler-utils: PDF processing (pdfinfo, pdftotext)
# - tesseract-ocr: OCR for images and scanned PDFs
# - tesseract-ocr-eng: English language pack for OCR
# - tesseract-ocr-all: All languages (optional, adds ~400MB)
# - libgl1: OpenGL support for image processing
# - libreoffice: MS Office document conversion (optional but recommended)
# - ffmpeg: Audio/video processing
# - build-essential: Compiling Python packages
# - libpq-dev: PostgreSQL development headers
# =============================================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libsndfile1 \
    ffmpeg \
    # PDF and image processing
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    # File type detection
    libmagic-dev \
    # Image processing (OpenCV dependency)
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # Browser for PO Token generation (yt-dlp-getpot-wpc)
    chromium \
    chromium-driver \
    # MS Office support (optional - uncomment if needed)
    # libreoffice \
    # Cleaning
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Verify tesseract installation
RUN tesseract --version

# ============================================================================
# Builder Stage - Install Python packages
# ============================================================================
FROM base AS builder

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Copy ONLY requirements file (best caching)
COPY requirements-docker.txt ./

# Install with specific resolver options to avoid backtracking
RUN pip install --upgrade pip && \
    pip install --use-deprecated=legacy-resolver -r requirements-docker.txt

# Verify unstructured installation and available parsers
RUN python -c "from unstructured.partition.auto import partition; print('✓ Unstructured installed successfully')" || echo "⚠ Unstructured import warning"

# Pre-download removed (Kokoro replaced by Google TTS)

# ============================================================================
# Runtime Stage
# ============================================================================
FROM base AS runtime

# Create app user with home directory
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser scripts ./scripts
# youtube cookies and tokens are optional and should be mounted as volumes or secrets if needed

# Create data directories and cache folders
RUN mkdir -p data/uploads data/audio_output logs .cache/huggingface .cache/fastembed && \
    chown -R appuser:appuser /app

# Set cache directories to writable locations (HF_HOME is the modern standard)
ENV HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
    # Unstructured settings
    UNSTRUCTURED_CACHE_DIR=/app/.cache/unstructured

USER appuser

# Pre-download models to bake them into the image
# This prevents 30s+ timeout on startup and OOM kills
RUN python scripts/download_models.py

EXPOSE 8000

# Lighter health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health/liveness', timeout=5)" || exit 1

# Default: Run API with embedded worker (combined mode)
# ENABLE_EMBEDDED_WORKER=true is the default
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# ============================================================================
# Worker variant (for separate deployment when scaling)
# Use this target only if you need to run worker separately
# Remember to set ENABLE_EMBEDDED_WORKER=false on the API service
# ============================================================================
FROM runtime AS worker
ENV ENABLE_EMBEDDED_WORKER=false
CMD ["python", "-m", "src.services.queue.worker"]
