import sys
from pathlib import Path

# Path manipulation for direct execution
if __name__ == "__main__":
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

load_dotenv()

import os
import asyncio
import tempfile
import shutil
import time
from typing import Optional, Dict, Any, List
import yt_dlp
from yt_dlp.utils import DownloadError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)
from youtube_transcript_api._errors import CouldNotRetrieveTranscript
import assemblyai as aai
from datetime import datetime, timezone
from src.schemas.document import UnifiedDocument, DocumentType, ProcessingStatus
from src.utils.exceptions import YoutubeProcessingError
from src.config import get_settings
from src.services.ingestion.chunk_manager import (
    apply_chunking_to_document_non_destructive,
)
from loguru import logger
import uuid
import re
import random

from src.services.embeddings.embedding_config import (
    get_llamaindex_embed_model,
    configure_llamaindex_embed_model,
)

if __name__ == "__main__":
    get_settings.cache_clear()

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds
RETRY_DELAY_MAX = 30  # seconds


def exponential_backoff(
    attempt: int, base: float = RETRY_DELAY_BASE, max_delay: float = RETRY_DELAY_MAX
) -> float:
    """Calculate exponential backoff delay with jitter."""
    delay = min(base * (2**attempt), max_delay)
    jitter = random.uniform(0, delay * 0.3)  # 30% jitter
    return delay + jitter


class YoutubeProcessor:
    def __init__(self):
        self.api_key = get_settings().assemblyai.api_key
        self.temp_dir = Path(tempfile.gettempdir()) / "notebookllm_youtube"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        aai.settings.api_key = self.api_key
        self.ffmpeg_available = self._check_ffmpeg()
        logger.info(
            f"YoutubeProcessor initialized (ffmpeg: {'available' if self.ffmpeg_available else 'not available'})"
        )

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available in the system."""
        return shutil.which("ffmpeg") is not None

    # Regex patterns for extracting video ID (more robust than simple split)
    VIDEO_ID_PATTERNS = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})",
    ]

    def extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract video ID from various YouTube URL formats.

        Args:
            url: YouTube URL

        Returns:
            11-character video ID or None if not found
        """
        for pattern in self.VIDEO_ID_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def fetch_transcript(
        self, url: str, preferred_languages: List[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch transcript using youtube-transcript-api with retry logic.

        This approach is faster and more reliable than downloading audio and transcribing,
        but only works if the video has captions available.

        Args:
            url: YouTube video URL
            preferred_languages: List of language codes to try (default: ['en'])

        Returns:
            Dict with success status and transcript data or error message
        """
        if preferred_languages is None:
            preferred_languages = ["en"]

        video_id = self.extract_video_id(url)
        if not video_id:
            return {
                "success": False,
                "error_message": f"Could not extract video ID from URL: {url}",
            }

        # Retry logic for transient errors (rate limiting)
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Fetching transcript for video {video_id} (attempt {attempt + 1}/{MAX_RETRIES})"
                )

                # Fetch transcript using youtube-transcript-api
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

                # Find the best matching transcript
                transcript_obj = transcript_list.find_transcript(preferred_languages)

                # Fetch the actual data
                snippets = transcript_obj.fetch()

                language = transcript_obj.language_code
                is_auto_generated = transcript_obj.is_generated

                if not snippets:
                    return {
                        "success": False,
                        "video_id": video_id,
                        "error_message": "Transcript is empty",
                    }

                # Adapter class to match expected snippet interface
                class SnippetAdapter:
                    def __init__(self, data):
                        self.text = data.get("text", "")
                        self.start = data.get("start", 0.0)
                        self.duration = data.get("duration", 0.0)

                snippets = [SnippetAdapter(s) for s in snippets]

                # Format transcript with timestamps
                formatted_transcript = self._format_transcript_with_timestamps(snippets)

                # Calculate total duration from last snippet
                last_snippet = snippets[-1]
                total_duration = last_snippet.start + last_snippet.duration

                return {
                    "success": True,
                    "video_id": video_id,
                    "transcript": formatted_transcript["text"],
                    "transcript_with_timestamps": formatted_transcript[
                        "with_timestamps"
                    ],
                    "language": language,
                    "is_auto_generated": is_auto_generated,
                    "duration_seconds": total_duration,
                    "segment_count": len(snippets),
                    "snippets": snippets,
                }

            except (CouldNotRetrieveTranscript, Exception) as e:
                # Rate limited or other transient error - retry with backoff
                error_str = str(e).lower()
                is_rate_limit = (
                    "rate" in error_str
                    or "blocked" in error_str
                    or "429" in error_str
                    or "too many" in error_str
                )

                if is_rate_limit:
                    last_error = f"Rate limited by YouTube: {str(e)}"
                    logger.warning(
                        f"YouTube rate limited (attempt {attempt + 1}/{MAX_RETRIES}): {last_error}"
                    )
                elif isinstance(e, TranscriptsDisabled):
                    return {
                        "success": False,
                        "video_id": video_id,
                        "error_message": "Transcripts are disabled for this video",
                    }
                elif isinstance(e, NoTranscriptFound):
                    return {
                        "success": False,
                        "video_id": video_id,
                        "error_message": "No transcript available for this video",
                    }
                elif isinstance(e, VideoUnavailable):
                    return {
                        "success": False,
                        "video_id": video_id,
                        "error_message": "Video is unavailable (private, deleted, or region-locked)",
                    }
                else:
                    last_error = str(e)
                    logger.warning(
                        f"Transcript fetch error (attempt {attempt + 1}/{MAX_RETRIES}): {last_error}"
                    )

                if attempt < MAX_RETRIES - 1:
                    delay = exponential_backoff(attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                continue

        # All retries exhausted
        return {
            "success": False,
            "video_id": video_id,
            "error_message": f"Failed after {MAX_RETRIES} attempts: {last_error}",
        }

    def _format_transcript_with_timestamps(self, snippets: List) -> Dict[str, str]:
        """
        Format transcript snippets into readable text with and without timestamps.

        Args:
            snippets: List of FetchedTranscriptSnippet objects

        Returns:
            Dict with 'text' and 'with_timestamps' formatted strings
        """
        if not snippets:
            return {"text": "", "with_timestamps": ""}

        lines_with_timestamps = []
        lines_plain = []

        for snippet in snippets:
            text = snippet.text.strip() if snippet.text else ""
            if not text:
                continue

            # Format timestamp
            timestamp = self._format_timestamp(snippet.start)
            lines_with_timestamps.append(f"[{timestamp}] {text}")
            lines_plain.append(text)

        return {
            "with_timestamps": "\n".join(lines_with_timestamps),
            "text": " ".join(lines_plain),
        }

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds into HH:MM:SS or MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def _enhanced_download_audio(self, url: str) -> str:
        """
        Enhanced audio download with improved headers and retry logic.
        Uses yt-dlp with better configuration to bypass YouTube restrictions.

        Includes:
        - Multiple client fallback (web, ios, android, mweb)
        - PO Token support
        - Proxy support from environment
        - Retry logic with exponential backoff
        - Cookie file support (REQUIRED for production)
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            raise ValueError("Could not extract video ID from URL")

        # Check for any existing audio file for this video
        existing_files = list(self.temp_dir.glob(f"{video_id}.*"))
        # Filter for common audio/video formats
        audio_formats = {".m4a", ".mp4", ".webm", ".opus", ".ogg", ".mp3", ".wav"}
        existing_audio = [
            f for f in existing_files if f.suffix.lower() in audio_formats
        ]

        if existing_audio:
            logger.info(f"Audio already exists: {existing_audio[0]}")
            return str(existing_audio[0])

        # Expected path (preferred format)
        expected_path = self.temp_dir / f"{video_id}.m4a"

        logger.info(f"Downloading audio from: {url}")

        # Get proxy from environment if available
        proxy = (
            os.environ.get("YOUTUBE_PROXY")
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("HTTP_PROXY")
        )
        if proxy:
            logger.info(f"Using proxy: {proxy}")

        # Cookie handling - check multiple locations
        cookies_file = None

        # Log all checked paths for debugging
        checked_paths = []

        # Priority 1: Cookies from base64 environment variable (for easy secret passing)
        cookies_base64 = os.environ.get("YOUTUBE_COOKIES_BASE64")
        if cookies_base64:
            import base64

            try:
                cookie_content = base64.b64decode(cookies_base64).decode("utf-8")
                temp_cookie_file = self.temp_dir / "youtube_cookies.txt"
                with open(temp_cookie_file, "w") as f:
                    f.write(cookie_content)
                cookies_file = str(temp_cookie_file)
                logger.info(
                    "Using cookies from YOUTUBE_COOKIES_BASE64 environment variable"
                )
            except Exception as e:
                logger.warning(f"Failed to decode YOUTUBE_COOKIES_BASE64: {e}")

        # Priority 2: Custom path from environment variable
        if not cookies_file:
            custom_cookie_path = os.environ.get("YOUTUBE_COOKIES_PATH")
            if custom_cookie_path and Path(custom_cookie_path).exists():
                cookies_file = custom_cookie_path
                logger.info(
                    f"Using custom cookies file from YOUTUBE_COOKIES_PATH: {cookies_file}"
                )

        # Priority 3: Check common cookie file locations
        if not cookies_file:
            possible_cookie_paths = [
                Path("/app/cookies.txt"),  # Coolify volume mount
                Path("/app/youtube_cookies.txt"),
                Path("/cookies.txt"),
                Path("/youtube_cookies.txt"),
                Path.home() / ".config" / "yt-dlp" / "cookies.txt",
                Path.home() / ".cookies" / "youtube.txt",
                Path("cookies.txt"),
                Path("youtube_cookies.txt"),
            ]
            for cookie_path in possible_cookie_paths:
                if cookie_path.exists():
                    cookies_file = str(cookie_path)
                    logger.info(f"Using cookies file: {cookies_file}")
                    break

        # Priority 5: Check for cookies.txt in project directories (for development)
        if not cookies_file:
            project_cookie_paths = [
                Path(__file__).parent.parent.parent.parent
                / "youtube_cookies.txt",  # /backend/youtube_cookies.txt
                Path(__file__).parent.parent.parent.parent
                / "cookies.txt",  # /backend/cookies.txt
                Path(__file__).parent.parent.parent / "cookies.txt",  # /cookies.txt
            ]
            for cookie_path in project_cookie_paths:
                if cookie_path.exists():
                    cookies_file = str(cookie_path)
                    logger.info(f"Using project cookies file: {cookies_file}")
                    break

        # Priority 4: Try browser cookies only in non-production
        cookies_from_browser = None
        if not cookies_file:
            is_production = os.environ.get("COOLIFY_ENVIRONMENT") or os.environ.get(
                "PRODUCTION"
            )
            if not is_production:
                import platform

                system = platform.system()
                if system == "Windows":
                    cookies_from_browser = "chrome"
                elif system == "Darwin":
                    cookies_from_browser = "chrome"
                elif system == "Linux":
                    try:
                        cookies_from_browser = "chrome"
                    except Exception:
                        pass

        if not cookies_file and not cookies_from_browser:
            logger.warning(
                "=============================================================\n"
                "WARNING: No YouTube cookies found!\n"
                "YouTube will likely block requests with 'Sign in to confirm you're not a bot'\n"
                "\n"
                "To fix this in production:\n"
                "  Option 1: Set YOUTUBE_COOKIES_PATH to cookie file path\n"
                "  Option 2: Set YOUTUBE_COOKIES_BASE64 with base64-encoded cookies\n"
                "  Option 3: Mount cookies.txt to /app/cookies.txt\n"
                "\n"
                "To generate cookies:\n"
                "  yt-dlp --cookies-from-browser chrome --write-subs https://www.youtube.com/watch?v=EXAMPLE\n"
                "============================================================="
            )

        # Priority 2: Check common cookie file locations
        if not cookies_file:
            possible_cookie_paths = [
                Path("/app/cookies.txt"),  # Coolify volume mount
                Path("/app/youtube_cookies.txt"),
                Path("/cookies.txt"),
                Path.home() / ".config" / "yt-dlp" / "cookies.txt",
                Path.home() / ".cookies" / "youtube.txt",
                Path("cookies.txt"),
            ]
            for cookie_path in possible_cookie_paths:
                if cookie_path.exists():
                    cookies_file = str(cookie_path)
                    logger.info(f"Using cookies file: {cookies_file}")
                    break

        # Priority 3: Try browser cookies only in development
        cookies_from_browser = None
        if not cookies_file:
            is_production = os.environ.get("COOLIFY_ENVIRONMENT") or os.environ.get(
                "PRODUCTION"
            )
            if not is_production:
                import platform

                system = platform.system()
                if system == "Windows":
                    cookies_from_browser = "chrome"
                elif system == "Darwin":
                    cookies_from_browser = "chrome"
                elif system == "Linux":
                    try:
                        cookies_from_browser = "chrome"
                    except Exception:
                        pass

        if not cookies_file and not cookies_from_browser:
            logger.warning(
                "No YouTube cookies found! This will likely fail for most YouTube videos. "
                "Set YOUTUBE_COOKIES_PATH environment variable or mount cookies.txt to /app/"
            )

        # PO Token: Now using automatic provider (yt-dlp-getpot-wpc)
        # The plugin will automatically generate PO Tokens using browser automation
        # No manual PO Token needed anymore!
        logger.info(
            "Using yt-dlp-getpot-wpc for automatic PO Token generation. "
            "No manual token refresh needed!"
        )

        def create_ydl_opts(client_priority: list = None) -> dict:
            """Create yt-dlp options with specified client priority."""
            if client_priority is None:
                # Default client priority - use mweb with automatic PO Token
                client_priority = ["mweb", "web", "ios", "android"]

            if self.ffmpeg_available:
                format_selector = "bestaudio/best"
                postprocessors = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "m4a",
                    }
                ]
            else:
                format_selector = (
                    "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
                )
                postprocessors = []

            ydl_opts = {
                "format": format_selector,
                "outtmpl": str(self.temp_dir / "%(id)s.%(ext)s"),
                "quiet": False,
                "no_warnings": False,
                "retries": 3,
                "fragment_retries": 3,
                # Bot detection bypass - try multiple clients
                # Use wpc provider for automatic PO Token generation (fallback)
                "extractor_args": {
                    "youtube": {
                        "player_client": client_priority,
                        "player_skip": ["webpage", "configs", "js", "initial"],
                        "player_ingest_nsig": True,
                    },
                },
                # User agent
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-us,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                },
            }

            # Support for manual PO Token via environment variables
            po_token = os.environ.get("YOUTUBE_PO_TOKEN")
            visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")
            
            if po_token:
                logger.info("Using manual PO Token from environment variables")
                po_token_args = []
                for client in client_priority:
                    # Provide token for each client in the format client+token
                    po_token_args.append(f"{client}+{po_token}")
                
                ydl_opts["extractor_args"]["youtube"]["po_token"] = po_token_args
                
                # Visitor data is highly recommended when using PO token
                if visitor_data:
                    logger.info("Using manual Visitor Data from environment variables")
                    ydl_opts["http_headers"]["X-Goog-Visitor-Id"] = visitor_data
            
            # PO Token is normally handled automatically by yt-dlp-getpot-wpc plugin
            # unless provided manually above
            
            if postprocessors:
                ydl_opts["postprocessors"] = postprocessors

            if proxy:
                ydl_opts["proxy"] = proxy

            # Pass cookies to yt-dlp if available
            if cookies_file:
                ydl_opts["cookiefile"] = cookies_file
                logger.info(f"Passing cookies to yt-dlp: {cookies_file}")

            return ydl_opts

        def attempt_download(opts: dict, attempt_num: int = 1) -> tuple:
            """Attempt download with given options, return (success, filepath_or_error)"""
            try:
                logger.info(
                    f"Download attempt {attempt_num} with client: {opts.get('extractor_args', {}).get('youtube', {}).get('player_client', ['unknown'])}"
                )

                with yt_dlp.YoutubeDL(opts) as ydl:
                    error_code = ydl.download([url])

                    if error_code != 0:
                        return (
                            False,
                            f"yt-dlp download failed with error code: {error_code}",
                        )

                # Check for downloaded file
                downloaded_files = list(self.temp_dir.glob(f"{video_id}.*"))
                if not downloaded_files:
                    return False, f"Downloaded file not found for video {video_id}"

                downloaded_file = downloaded_files[0]

                if downloaded_file.suffix.lower() == ".m4a":
                    logger.info(f"Audio downloaded successfully: {downloaded_file}")
                    return True, str(downloaded_file)

                if not self.ffmpeg_available:
                    logger.warning(
                        f"Downloaded {downloaded_file.suffix} format without ffmpeg"
                    )
                    m4a_path = downloaded_file.with_suffix(".m4a")
                    if m4a_path != downloaded_file:
                        downloaded_file.rename(m4a_path)
                    return True, str(m4a_path)

                if expected_path.exists():
                    return True, str(expected_path)
                else:
                    return True, str(downloaded_file)

            except Exception as e:
                error_msg = str(e)
                # Check for specific error types that warrant retry
                if any(
                    x in error_msg.lower()
                    for x in ["403", "429", "rate", "blocked", "unavailable"]
                ):
                    return False, f"Retryable error: {error_msg}"
                return False, error_msg

        # Client fallback chain - try different clients in order
        client_chains = [
            ["web", "ios", "android"],  # Standard clients
            ["mweb"],  # Mobile web (may work when others fail)
            ["web", "android"],  # Try Android as fallback
            ["android"],  # Last resort
        ]

        # Try with cookies first if available
        if cookies_file or cookies_from_browser:
            ydl_opts = create_ydl_opts()
            if cookies_file:
                ydl_opts["cookiefile"] = cookies_file
            elif cookies_from_browser:
                try:
                    ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
                except Exception as e:
                    logger.warning(f"Failed to get browser cookies: {e}")
                    ydl_opts.pop("cookiesfrombrowser", None)

            success, result = attempt_download(ydl_opts)
            if success:
                return result

            # Check if error is cookie-related
            error_str = result.lower()
            if any(x in error_str for x in ["decode", "dpapi", "cookie", "sign in"]):
                logger.warning(f"Cookie error, trying without: {result}")
            else:
                # Non-cookie error, try other clients
                for clients in client_chains:
                    ydl_opts = create_ydl_opts(clients)
                    success, result = attempt_download(ydl_opts)
                    if success:
                        return result

        # Try without cookies, different client chains
        for clients in client_chains:
            ydl_opts = create_ydl_opts(clients)
            success, result = attempt_download(ydl_opts)
            if success:
                return result

            # Check if we should retry with different client
            error_str = result.lower()
            if "po token" in error_str or "requires po token" in error_str:
                logger.warning(f"PO Token required, trying with mweb client")
                continue  # Try next client chain

        # Final attempt with HLS fallback
        logger.info("Trying HLS protocol as last resort...")
        ydl_opts = create_ydl_opts(["web"])
        ydl_opts["extractor_args"]["youtube"]["player_client"] = ["web"]
        ydl_opts["protocol"] = "m3u8_native"  # Force HLS

        success, result = attempt_download(ydl_opts)
        if success:
            return result

        raise YoutubeProcessingError(
            f"Failed to download YouTube audio after all attempts: {result}"
        )

    def download_audio(self, url: str) -> str:
        """
        Download audio from YouTube video.

        Strategy:
        1. First try to fetch transcript using youtube-transcript-api (faster, no API cost)
        2. If transcript fails, fall back to yt-dlp audio download + AssemblyAI transcription

        Returns:
            Path to downloaded audio file (for transcript approach, this is a temp file with transcript text)
        """
        # First, try to fetch transcript
        transcript_result = self.fetch_transcript(url)

        if transcript_result["success"]:
            logger.info(
                f"Successfully fetched transcript for video {transcript_result['video_id']}"
            )
            # Save transcript to a temporary file for compatibility with existing code
            transcript_path = (
                self.temp_dir / f"{transcript_result['video_id']}_transcript.txt"
            )
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript_result["transcript"])
            logger.info(f"Transcript saved to: {transcript_path}")
            return str(transcript_path)
        else:
            logger.warning(
                f"Transcript fetch failed: {transcript_result['error_message']}"
            )
            logger.info(
                "Falling back to yt-dlp audio download + AssemblyAI transcription"
            )
            # Fall back to yt-dlp approach
            return self._enhanced_download_audio(url)

    async def get_video_title(self, url: str) -> str:
        """Fetch video title using yt-dlp."""
        try:
            # Use asyncio.to_thread since yt-dlp is blocking
            def fetch_info():
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info.get("title", "Unknown Title")

            return await asyncio.to_thread(fetch_info)
        except Exception as e:
            logger.warning(f"Failed to fetch video title: {e}")
            video_id = self.extract_video_id(url)
            return f"YouTube Video {video_id}"

    async def process_video(
        self, url: str, cleanup_audio: bool = True
    ) -> UnifiedDocument:
        """
        Process YouTube video and return a UnifiedDocument with transcript chunks.

        Strategy:
        1. Try to get transcript from YouTube API (fast, no external API cost)
        2. If transcript unavailable, download audio and transcribe with AssemblyAI
        """
        audio_path = None
        transcript_snippets = None
        is_transcript_approach = False

        try:
            settings = get_settings()
            video_id = self.extract_video_id(url)

            # Fetch title (parallelizable but fast enough to await)
            video_title = await self.get_video_title(url)
            # Sanitize title for filename
            safe_title = "".join(
                [c for c in video_title if c.isalnum() or c in (" ", "-", "_")]
            ).strip()
            filename = f"{safe_title}.txt" if safe_title else f"youtube_{video_id}.txt"

            # First, try to fetch transcript from YouTube API
            logger.info(f"Attempting to fetch transcript from YouTube API for: {url}")
            transcript_result = self.fetch_transcript(url)

            if transcript_result["success"]:
                # Use YouTube's existing transcript (NoobBook approach)
                logger.info(f"Successfully fetched transcript from YouTube API")
                transcript_snippets = transcript_result["snippets"]
                is_transcript_approach = True

                # Create a dummy "audio path" for compatibility
                audio_path = transcript_result["transcript"]
            else:
                # Fall back to yt-dlp + AssemblyAI
                logger.warning(
                    f"YouTube API transcript failed: {transcript_result['error_message']}"
                )
                logger.info(
                    "Falling back to yt-dlp audio download + AssemblyAI transcription"
                )

                audio_path = await asyncio.to_thread(self._enhanced_download_audio, url)

                # Transcribe with AssemblyAI
                config = aai.TranscriptionConfig(
                    language_code="en",
                    speaker_labels=True,
                    punctuate=True,
                    format_text=True,
                )
                logger.info(f"Transcribing audio with config: {config}")
                transcriber = aai.Transcriber(config=config)
                transcript = transcriber.transcribe(audio_path)

                if hasattr(transcript, "error") and transcript.error:
                    raise YoutubeProcessingError(
                        f"Transcription failed: {transcript.error}"
                    )

                logger.info(f"AssemblyAI transcription completed successfully")

                # Convert AssemblyAI transcript to our format
                def safe_getattr_ai(obj, attr_name, default=None):
                    try:
                        return getattr(obj, attr_name, default)
                    except AttributeError:
                        return default

                # Build snippets from AssemblyAI response
                utterances = safe_getattr_ai(transcript, "utterances")
                transcript_text = safe_getattr_ai(transcript, "text")

                if utterances:
                    transcript_snippets = []
                    for utterance in utterances:
                        start = safe_getattr_ai(utterance, "start", 0) or 0
                        duration = safe_getattr_ai(utterance, "end", 0) or 0
                        text = safe_getattr_ai(utterance, "text", "")
                        transcript_snippets.append(
                            {"text": text, "start": start, "duration": duration - start}
                        )
                elif transcript_text:
                    # Plain text, no timestamps
                    transcript_snippets = [
                        {"text": transcript_text, "start": 0, "duration": 0}
                    ]

            # Log preview of snippets
            if transcript_snippets:
                preview_len = min(3, len(transcript_snippets))
                preview = [
                    s.get("text", "")[:50]
                    if isinstance(s, dict)
                    else getattr(s, "text", "")[:50]
                    for s in transcript_snippets[:preview_len]
                ]
                logger.info(f"Transcript preview: {preview}")

            # Common processing for both approaches
            now = datetime.now(timezone.utc)
            doc = UnifiedDocument(
                id=uuid.uuid4(),
                user_id=settings.anonymous_user_id,
                filename=filename,
                source_type=DocumentType.AUDIO,
                status=ProcessingStatus.COMPLETED,
                storage_path=str(audio_path) if not is_transcript_approach else "",
                created_at=now,
                updated_at=now,
                metadata={
                    "source": "youtube",
                    "video_id": video_id,
                    "source_url": url,
                    "title": video_title,
                    "transcript_approach": is_transcript_approach,
                },
            )

            # Process transcript snippets
            if transcript_snippets:
                logger.info(
                    f"Processing {len(transcript_snippets)} transcript segments"
                )
                for i, snippet in enumerate(transcript_snippets):
                    text = (
                        snippet.get("text", "")
                        if isinstance(snippet, dict)
                        else getattr(snippet, "text", "")
                    )
                    if not text or not text.strip():
                        continue

                    # Get start time
                    if isinstance(snippet, dict):
                        start = snippet.get("start", 0) or 0
                        duration = snippet.get("duration", 0) or 0
                    else:
                        start = getattr(snippet, "start", 0) or 0
                        duration = getattr(snippet, "duration", 0) or 0

                    end = start + duration

                    doc.add_chunk(
                        content=text.strip(),
                        chunk_index=i,
                        start_time=start,
                        end_time=end,
                        metadata={
                            "source": "youtube",
                            "source_id": video_id,
                            "source_url": url,
                            "segment": i,
                            "video_id": video_id,
                        },
                    )
            else:
                logger.warning("No transcript segments available to process")

            # Apply config-driven sentence-aware sub-chunking
            overlap = max(
                0, min(settings.rag.chunk_overlap, settings.rag.chunk_size // 2)
            )
            chunking_strategy = settings.rag.chunking_strategy
            embed_model = None

            if chunking_strategy == "semantic" or chunking_strategy == "auto":
                try:
                    embed_model = get_llamaindex_embed_model()
                    if embed_model is None:
                        configure_llamaindex_embed_model()
                        embed_model = get_llamaindex_embed_model()
                except (ImportError, RuntimeError, ValueError) as e:
                    logger.warning(
                        f"Failed to load embedding model for semantic chunking: {e}. Falling back to sentence chunking."
                    )
                    chunking_strategy = "sentence"
                    embed_model = None

            doc = apply_chunking_to_document_non_destructive(
                doc,
                chunk_size=settings.rag.chunk_size,
                chunk_overlap=overlap,
                respect_sentence_boundary=True,
                strategy=chunking_strategy,
                embed_model=embed_model,
            )
            return doc
        except YoutubeProcessingError:
            raise
        except Exception as e:
            logger.error(f"Failed to process YouTube video: {e}", exc_info=True)
            raise YoutubeProcessingError(
                f"Failed to process YouTube video: {str(e)}"
            ) from e
        finally:
            # Cleanup: only remove actual audio files, not transcript text files
            if (
                cleanup_audio
                and audio_path
                and os.path.exists(audio_path)
                and not is_transcript_approach
            ):
                try:
                    os.remove(audio_path)
                    logger.info(f"Audio file cleaned up: {audio_path}")
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup audio file {audio_path}: {cleanup_error}"
                    )
