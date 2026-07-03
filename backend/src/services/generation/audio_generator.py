import os
import uuid
import wave
import base64
import asyncio
import tempfile
import shutil
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import httpx

# Audio Processing
from pydub import AudioSegment
from loguru import logger

from src.config import get_settings
from src.schemas.content import PodcastScript
from src.services.storage import get_storage_service


# Gemini TTS configuration
# Uses the standard Gemini API key (GEMINI_API_KEY) — no Google Cloud service
# account required. The model returns raw signed 16-bit PCM audio.
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
GEMINI_TTS_SAMPLE_RATE = 24000
GEMINI_TTS_CHANNELS = 1
GEMINI_TTS_SAMPLE_WIDTH = 2  # 16-bit PCM


class AudioGenerator:
    """
    Memory-efficient podcast audio generator using Google Cloud TTS.

    Key improvements for OOM prevention:
    - Disk-based batch processing (not memory)
    - Semaphore-controlled concurrency (respects API quotas)
    - Retry logic with exponential backoff
    - ffmpeg streaming concatenation
    - Proper temp file cleanup
    """

    def __init__(self):
        self.settings = get_settings()
        self.storage = get_storage_service()

        # Gemini TTS uses the standard Gemini API key — no GCP service account.
        self.api_key = self.settings.llm.gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.model = GEMINI_TTS_MODEL
        # `client` retained as a readiness flag for existing call sites / guards.
        self.client = bool(self.api_key)
        if self.client:
            logger.info(f"Gemini TTS ready (model={self.model})")
        else:
            logger.error(
                "GEMINI_API_KEY is not set — Gemini TTS unavailable, cannot generate podcast audio."
            )

        # Create temp directory for processing
        self.temp_dir = Path(tempfile.mkdtemp(prefix="podcast_tts_"))
        self.output_dir = self.temp_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Concurrency control: keep it low. The preview TTS model has tight
        # per-minute limits on the free tier, so serialize-ish to avoid 429s.
        self.tts_semaphore = asyncio.Semaphore(2)

        # Batch size for processing clips (limits memory per batch)
        self.batch_size = 2

        # Retry configuration
        self.max_retries = 4
        self.retry_base_delay = 2.0  # seconds

        # Voice Mapping - Gemini prebuilt voices.
        # Full list: https://ai.google.dev/gemini-api/docs/speech-generation#voices
        # Kore = firm, Puck = upbeat, Charon = informative, Aoede = breezy.
        self.voice_map = {
            "Host (Jane)": "Kore",       # Warm, clear host
            "Expert (Tom)": "Charon",    # Informative, authoritative
            "default": "Kore",
        }
        # Rotating fallback voices for any speaker not in the map, so multiple
        # speakers still sound distinct.
        self._fallback_voices = ["Kore", "Charon", "Puck", "Aoede", "Fenrir"]

    def __del__(self):
        """Cleanup temp directory on object destruction."""
        try:
            if hasattr(self, "temp_dir") and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Could not cleanup temp directory: {e}")

    def _clean_text_for_tts(self, text: str) -> str:
        """Clean text to improve TTS quality."""
        clean_text = text.strip()

        # Basic cleanup - Studio voices handle punctuation well
        clean_text = clean_text.replace("...", ".")
        clean_text = clean_text.replace("!!", "!")
        clean_text = clean_text.replace("??", "?")

        # Ensure ending punctuation for better cadence
        if clean_text and not clean_text[-1] in ".!?":
            clean_text += "."

        return clean_text

    def _resolve_voice(self, speaker: str) -> str:
        """Map a script speaker to a Gemini prebuilt voice name."""
        if speaker in self.voice_map:
            return self.voice_map[speaker]
        # Deterministic fallback so the same speaker always gets the same voice.
        idx = abs(hash(speaker)) % len(self._fallback_voices)
        return self._fallback_voices[idx]

    def _write_wav(self, pcm_bytes: bytes, dest: Path) -> None:
        """Wrap raw signed 16-bit PCM into a playable WAV container."""
        with wave.open(str(dest), "wb") as wf:
            wf.setnchannels(GEMINI_TTS_CHANNELS)
            wf.setsampwidth(GEMINI_TTS_SAMPLE_WIDTH)
            wf.setframerate(GEMINI_TTS_SAMPLE_RATE)
            wf.writeframes(pcm_bytes)

    async def _generate_clip_with_retry(
        self, text: str, speaker: str, clip_index: int
    ) -> Optional[Path]:
        """
        Generate audio for a single clip via Gemini TTS with retry logic.
        Decodes the returned PCM and saves it as a WAV temp file.

        Args:
            text: Text to convert to speech
            speaker: Speaker identifier (maps to voice)
            clip_index: Index for temp file naming

        Returns:
            Path to temp audio file, or None if failed
        """
        if not self.client:
            logger.error("Gemini TTS not initialized (missing GEMINI_API_KEY)")
            return None

        clean_text = self._clean_text_for_tts(text)
        if not clean_text:
            return None

        voice_name = self._resolve_voice(speaker)
        url = GEMINI_TTS_ENDPOINT.format(model=self.model)
        payload = {
            "contents": [{"parts": [{"text": clean_text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice_name}
                    }
                },
            },
        }

        async with self.tts_semaphore:
            for attempt in range(self.max_retries):
                try:
                    async with httpx.AsyncClient(timeout=120.0) as http:
                        resp = await http.post(
                            url,
                            params={"key": self.api_key},
                            json=payload,
                            headers={"Content-Type": "application/json"},
                        )

                    # Retryable statuses: rate limit + transient server errors
                    if resp.status_code in (429, 500, 502, 503):
                        wait_time = (2**attempt) * self.retry_base_delay
                        logger.warning(
                            f"Gemini TTS {resp.status_code} on clip {clip_index}, "
                            f"retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    if resp.status_code != 200:
                        logger.error(
                            f"Gemini TTS error {resp.status_code} for clip {clip_index}: "
                            f"{resp.text[:300]}"
                        )
                        return None

                    data = resp.json()
                    parts = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                    inline = next(
                        (p["inlineData"] for p in parts if "inlineData" in p), None
                    )
                    if not inline or not inline.get("data"):
                        logger.error(
                            f"Gemini TTS returned no audio for clip {clip_index}: {str(data)[:300]}"
                        )
                        return None

                    pcm_bytes = base64.b64decode(inline["data"])
                    temp_file = self.temp_dir / f"clip_{clip_index:04d}.wav"
                    self._write_wav(pcm_bytes, temp_file)

                    logger.debug(
                        f"Generated clip {clip_index} ({voice_name}): {temp_file} "
                        f"({len(pcm_bytes)} PCM bytes)"
                    )
                    return temp_file

                except Exception as e:
                    if attempt < self.max_retries - 1:
                        wait_time = (2**attempt) * self.retry_base_delay
                        logger.warning(
                            f"Error on clip {clip_index}, retrying in {wait_time}s: {e}"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to generate clip {clip_index} after {self.max_retries} attempts: {e}"
                        )
                        return None

            return None

    async def _process_batch(self, batch: List[Tuple[Any, int]]) -> List[Path]:
        """
        Process a batch of clips concurrently.

        Args:
            batch: List of (turn, index) tuples

        Returns:
            List of paths to successfully generated temp files
        """
        tasks = []
        for turn, idx in batch:
            if turn.text.strip():
                tasks.append(
                    self._generate_clip_with_retry(turn.text, turn.speaker, idx)
                )

        # Execute batch concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failures and exceptions
        successful = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch item {i} failed with exception: {result}")
            elif result is not None:
                successful.append(result)

        return successful

    async def _concatenate_with_ffmpeg(
        self,
        input_files: List[Path],
        output_path: Path,
        intro_silence_ms: int = 500,
        inter_speaker_silence_ms: int = 300,
    ) -> None:
        """
        Concatenate audio files using ffmpeg (memory-efficient streaming).

        This avoids loading all AudioSegments into memory by using ffmpeg's
        concat demuxer which streams files sequentially.

        Args:
            input_files: List of audio file paths to concatenate
            output_path: Output file path
            intro_silence_ms: Silence duration at start (ms)
            inter_speaker_silence_ms: Silence between clips (ms)
        """
        if not input_files:
            raise ValueError("No input files provided for concatenation")

        # Create concat list file for ffmpeg
        list_file = self.temp_dir / "concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for input_file in input_files:
                # For Windows, use forward slashes in paths for ffmpeg
                # ffmpeg accepts forward slashes on all platforms
                normalized_path = str(input_file).replace("\\", "/")
                f.write(f"file '{normalized_path}'\n")

        try:
            # Build ffmpeg command with silence insertion
            # Using adelay for intro silence and apad+atrim for inter-speaker gaps
            filter_complex = (
                f"adelay={intro_silence_ms}|{intro_silence_ms},"  # Intro silence
                f"asetpts=PTS-STARTPTS"  # Reset timestamps
            )

            import platform
            import subprocess
            import shutil

            # Find ffmpeg binary - on Windows we need the full path to avoid shell issues
            ffmpeg_path = shutil.which("ffmpeg")
            if ffmpeg_path:
                ffmpeg_cmd = ffmpeg_path
                logger.debug(f"Found ffmpeg at: {ffmpeg_cmd}")
            else:
                ffmpeg_cmd = "ffmpeg"
                logger.warning("ffmpeg not found in PATH, using 'ffmpeg'")

            cmd = [
                ffmpeg_cmd,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file).replace("\\", "/"),
                "-af",
                filter_complex,
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                "-ar",
                "24000",
                "-ac",
                "1",
                str(output_path).replace("\\", "/"),
            ]

            logger.debug(f"Running ffmpeg concat: {' '.join(cmd)}")

            # Use sync subprocess in thread to avoid Windows asyncio NotImplementedError
            # On Windows: use full path with shell=False to avoid shell escaping issues
            def run_ffmpeg():
                is_windows = platform.system() == "Windows"
                if is_windows:
                    # On Windows, use shell=False with full ffmpeg path to avoid shell escaping issues
                    # The | character in filter_complex would be interpreted as pipe by shell
                    result = subprocess.run(cmd, capture_output=True, shell=False)
                else:
                    # On Linux/Mac, use shell=False (default)
                    result = subprocess.run(cmd, capture_output=True, shell=False)
                return result

            result = await asyncio.to_thread(run_ffmpeg)

            if result.returncode != 0:
                stderr_text = (
                    result.stderr.decode("utf-8", errors="ignore")
                    if result.stderr
                    else "No error output"
                )
                stdout_text = (
                    result.stdout.decode("utf-8", errors="ignore")
                    if result.stdout
                    else "No stdout"
                )
                logger.error(f"ffmpeg failed with return code {result.returncode}")
                logger.error(f"ffmpeg stderr: {stderr_text}")
                logger.error(f"ffmpeg stdout: {stdout_text}")
                logger.error(f"ffmpeg command: {' '.join(cmd)}")
                raise RuntimeError(
                    f"ffmpeg concat failed (code {result.returncode}): {stderr_text}"
                )

            logger.debug(
                f"Successfully concatenated {len(input_files)} clips to {output_path}"
            )

        finally:
            # Clean up list file
            if list_file.exists():
                list_file.unlink(missing_ok=True)

    async def _get_audio_duration(self, audio_path: Path) -> float:
        """
        Get audio duration using ffprobe.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        import subprocess

        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path).replace("\\", "/"),
            ]

            # Use sync subprocess in thread to avoid Windows asyncio issues
            def run_ffprobe():
                result = subprocess.run(cmd, capture_output=True, shell=False)
                return result

            result = await asyncio.to_thread(run_ffprobe)

            if result.returncode == 0:
                duration = float(result.stdout.decode().strip())
                return duration
            else:
                # Fallback: use pydub (loads file but just for duration)
                logger.warning(f"ffprobe failed, using pydub fallback")
                audio = AudioSegment.from_file(audio_path)
                return len(audio) / 1000.0

        except Exception as e:
            logger.warning(
                f"Could not get duration with ffprobe, using pydub fallback: {e}"
            )
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0

    async def _cleanup_temp_files(self, files: List[Path]) -> None:
        """Clean up temporary files."""
        for file_path in files:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.debug(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.warning(f"Could not delete temp file {file_path}: {e}")

    async def generate_podcast_audio(
        self,
        script: PodcastScript,
        notebook_id: str,
        user_id: str,
        filename_prefix: str = "podcast",
    ) -> Optional[Tuple[str, str, float]]:
        """
        Generate full podcast audio from script using memory-efficient batch processing.

        Key improvements:
        - Processes clips in small batches to limit memory usage
        - Saves clips to disk instead of keeping in memory
        - Uses ffmpeg for streaming concatenation
        - Implements retry logic with exponential backoff
        - Respects Google API rate limits with semaphore

        Args:
            script: PodcastScript with dialogue turns
            notebook_id: Notebook identifier
            user_id: User identifier
            filename_prefix: Prefix for output filename

        Returns:
            Tuple of (storage_key, public_url, duration_seconds) or None if failed
        """
        logger.info(
            f"Starting memory-efficient TTS generation for podcast: {script.title}"
        )

        if not self.client:
            logger.error("Gemini TTS is not available (missing GEMINI_API_KEY).")
            return None

        # Prepare dialogue segments
        dialogue_segments = [
            (turn, i) for i, turn in enumerate(script.dialogue) if turn.text.strip()
        ]

        total_segments = len(dialogue_segments)
        if total_segments == 0:
            logger.error("No dialogue segments to process")
            return None

        logger.info(
            f"Processing {total_segments} segments in batches of {self.batch_size}"
        )

        # Process in batches to limit memory usage
        temp_files: List[Path] = []
        total_batches = (total_segments + self.batch_size - 1) // self.batch_size
        output_path: Optional[Path] = None

        try:
            for batch_num in range(total_batches):
                batch_start = batch_num * self.batch_size
                batch_end = min(batch_start + self.batch_size, total_segments)
                batch = dialogue_segments[batch_start:batch_end]

                logger.info(
                    f"Processing batch {batch_num + 1}/{total_batches}: segments {batch_start}-{batch_end - 1}"
                )

                # Process batch
                batch_files = await self._process_batch(batch)
                temp_files.extend(batch_files)

                logger.info(
                    f"Batch {batch_num + 1} complete: {len(batch_files)}/{len(batch)} successful"
                )

                # Brief pause between batches to allow GC and avoid rate limits
                if batch_num < total_batches - 1:
                    await asyncio.sleep(0.5)

            if not temp_files:
                logger.error("Failed to generate any audio clips")
                return None

            logger.info(
                f"Successfully generated {len(temp_files)}/{total_segments} clips. Concatenating..."
            )

            # Concatenate using ffmpeg (memory-efficient)
            output_filename = f"{filename_prefix}_{uuid.uuid4().hex[:8]}.mp3"
            output_path: Optional[Path] = self.output_dir / output_filename

            await self._concatenate_with_ffmpeg(
                temp_files,
                output_path,
                intro_silence_ms=500,
                inter_speaker_silence_ms=300,
            )

            # Get duration
            duration_seconds = await self._get_audio_duration(output_path)
            logger.info(f"Final audio duration: {duration_seconds:.2f}s")

            # Upload to storage
            bucket_name = self.settings.storage.private_bucket

            if user_id:
                storage_key = f"{user_id}/{notebook_id}/podcast/{output_filename}"
            else:
                storage_key = f"anonymous/{notebook_id}/podcast/{output_filename}"

            logger.info(f"Uploading to Storage ({bucket_name}/{storage_key})...")

            # Stream upload to avoid loading entire file into memory
            with open(output_path, "rb") as f:
                file_bytes = f.read()

            await self.storage.upload(
                file_data=file_bytes,
                path=storage_key,
                bucket=bucket_name,
                mime_type="audio/mpeg",
            )

            # Get public URL
            public_url = await self.storage.get_url(
                storage_key, bucket_name, private=True
            )

            logger.success(
                f"Podcast generation complete: {public_url} "
                f"(Duration: {duration_seconds:.2f}s, "
                f"Clips: {len(temp_files)}/{total_segments})"
            )

            return storage_key, public_url, duration_seconds

        except Exception as e:
            logger.error(f"Failed to generate podcast audio: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

        finally:
            # Cleanup: Remove all temp files
            logger.debug("Cleaning up temporary files...")
            await self._cleanup_temp_files(temp_files)
            # Safe cleanup of output_path - it may be None if exception occurred early
            if output_path is not None:
                await self._cleanup_temp_files([output_path])
