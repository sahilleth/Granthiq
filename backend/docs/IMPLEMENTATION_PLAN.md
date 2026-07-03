# Implementation Plan: Google Cloud TTS Migration

> **Objective**: Migrate from local `Kokoro` TTS to Google Cloud Text-to-Speech API to resolve OOM issues and improve voice quality with "Journey" voices.

---

## 1. Configuration & Secrets

### 1.1 Credential File
- **Source**: `D:\code\granthiq\backend\granthiq-487912-c43c81168609.json`
- **Action**: 
    - Ensure this file is added to `.gitignore` to prevent accidental commit.
    - Set environment variable `GOOGLE_APPLICATION_CREDENTIALS` to this path in `.env`.

### 1.2 Environment Variables (`.env`)
Update `.env` to include:
```bash
# Google Cloud credentials for TTS
GOOGLE_APPLICATION_CREDENTIALS=granthiq-487912-c43c81168609.json
```

---

## 2. Dependency Management

### 2.1 Clean `pyproject.toml` & `requirements-docker.txt`
- **Remove**:
    - `kokoro` (and its version constraints)
    - `misaki` or `phonemizer` if present (usually pulled by kokoro)
- **Add**:
    - `google-cloud-texttospeech>=2.14.1`
- **Keep**:
    - `torch`, `transformers`, `sentence-transformers` (Required for RAG embeddings, do NOT remove)

### 2.2 Clean `Dockerfile`
- **Remove**:
    - Line 51: `RUN python -c "import spacy; spacy.cli.download('en_core_web_sm')"` (Only used by Kokoro)

---

## 3. Code Refactoring

### 3.1 Refactor `src/services/generation/audio_generator.py`
Replace the entire `Kokoro` pipeline with `TextToSpeechAsyncClient`.

**Key Changes**:
1.  **Imports**: Remove `kokoro`, add `google.cloud.texttospeech`.
2.  **Initialization**: 
    - Initialize `TextToSpeechAsyncClient`.
3.  **Voice Mapping**:
    - `Host (Jane)` -> `en-US-Journey-F`
    - `Expert (Tom)` -> `en-US-Journey-D`
4.  **Generation Logic**:
    - Asynchronously call Google API for each dialogue turn.
    - Use `AudioEncoding.MP3`.
    - Stitch audio using `pydub` (keep this logic).

### 3.2 Update `src/services/generation/generators/podcast.py`
- (Check if any changes needed - likely just ensuring it calls the generator correctly, which should remains the same interface).

---

## 4. Verification steps
1.  **Build**: Run `uv sync` or `pip install -r requirements.txt` to verify dependency resolution.
2.  **Test**: Run a generation task.
3.  **Check**:
    - Audio quality (Journey voices).
    - Memory usage (should be significantly lower).
