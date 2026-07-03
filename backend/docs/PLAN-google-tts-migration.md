# Plan: Google Cloud TTS Migration (PLAN-google-tts-migration)

> **Goal**: Evaluate and plan the migration from local Kokoro TTS to Google Cloud TTS to resolve Out-Of-Memory (OOM) issues on the VPS while improving voice quality using Google's generative "Journey" voices.

---

## 1. Context & Problem
- **Current State**: Using `Kokoro` (local TTS model) which requires significant RAM to load PyTorch and model weights.
- **Problem**: The VPS runs out of memory (OOM) when loading the model, causing worker restarts.
- **Solution**: Offload TTS processing to Google Cloud Text-to-Speech API.

---

## 2. Proposed Architecture
- **Service**: Google Cloud Text-to-Speech API (v1beta1 for Journey voices).
- **Authentication**: Google Cloud Service Account via `GOOGLE_APPLICATION_CREDENTIALS`.
- **Audio Format**: MP3 (192kbps).
- **Storage**: Existing flow (upload generated MP3 to Supabase Storage).

### Voice Selection
We will use **Journey** voices for maximum expressiveness in the podcast format.

| Role | Voice ID | Gender | Style |
|------|----------|--------|-------|
| **Host (Jane)** | `en-US-Journey-F` | Female | Warm, engaging, conversational |
| **Expert (Tom)** | `en-US-Journey-D` | Male | Deep, authoritative, calm |

---

## 3. Implementation Steps

### Phase 1: Dependency Cleanup
We need to aggressively remove heavy dependencies to free up space immediately.
- **Remove**:
  - `kokoro`
  - `torch` (This is the big one, ~700MB+)
  - `espeak-ng` (System dependency in Dockerfile)
- **Add**:
  - `google-cloud-texttospeech`

### Phase 2: Authentication & Config
- **Environment Variable**: `GOOGLE_APPLICATION_CREDENTIALS` pointing to a JSON key file.
- **Alternative**: If running on GCP, use Workload Identity (no keys needed). *Assumption: VPS requires JSON key.*

### Phase 3: Code Refactor (`src/services/generation/audio_generator.py`)
- **Initialization**: Replace `KPipeline` with `TextToSpeechAsyncClient`.
- **Generation Logic**:
  - Convert `_generate_clip` to call `client.synthesize_speech`.
  - Use `SSML` if we need specific pauses or emphasis (optional for now).
  - Return `AudioContent` bytes directly.
- **Stitching**: Keep `pydub` for combining the clips (AudioSegment handling).

### Phase 4: Verification
- **Test**: Generate a 1-minute podcast.
- **Monitor**: Check RAM usage during generation (should be minimal).

---

## 4. Security Considerations
- **Credentials**: Google Service Account Key (JSON) must be handled securely.
  - **Do NOT** check the JSON file into git.
  - **Do** mount it as a volume or inject via specific secure env var in production.
- **Least Privilege**: The Service Account should ONLY have `Cloud Text-to-Speech API User` role.

---

## 5. Cost Implication
- **Journey Voices**: ~$0.016 per 1k characters (Standard Tier pricing applies for standard, Premium for Journey/Studio).
- **Budget**: Ensure billing is enabled on the GCP project.

---

## 6. Action Plan
1.  **Start Implementation**: Run `/create` or confirm to proceed with code changes.
2.  **User Action**: Provide/Generate Google Cloud Service Account JSON key.
