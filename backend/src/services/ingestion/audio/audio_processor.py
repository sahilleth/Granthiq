import asyncio
import uuid
from src.config import get_settings
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from datetime import datetime, timezone
import assemblyai as aai
from src.schemas.document import UnifiedDocument, DocumentType, ProcessingStatus
from src.utils.exceptions import TranscriptionError
from loguru import logger
from src.services.ingestion.chunk_manager import chunk_text


async def _async_file_exists(path: Path) -> bool:
    """Async check if file exists using thread pool."""
    try:
        return await asyncio.to_thread(path.exists)
    except Exception:
        return False


async def _async_is_file(path: Path) -> bool:
    """Async check if path is a file using thread pool."""
    try:
        return await asyncio.to_thread(path.is_file)
    except Exception:
        return False


@dataclass
class SpeakerSegment:
    speaker : str
    start_time : float
    end_time : float
    text: str
    confidence : float

    def timestamp(self) -> str:
        def format_timestamp(seconds: float) -> str:
            minutes = int(seconds // 60)
            seconds = int(seconds % 60)
            return f"{minutes:02d}:{seconds:02d}"
        return f"{format_timestamp(self.start_time)} - {format_timestamp(self.end_time)}"


class AudioTranscriber:
    def __init__(self,api_key: str):
        self.api_key = api_key
        aai.settings.api_key = self.api_key

        self.supported_formats = {
            '.mp3', '.wav', '.m4a', '.aac', '.ogg', 
            '.flac', '.wma', '.opus', '.mp4', '.mov', '.avi'
        }
        
        logger.info("AudioTranscriber initialized with AssemblyAI")

    
    async def transcribe_audio(
        self,
         audio_path: str,
         enable_speaker_diarization: bool = True,
         enable_auto_punctuation: bool = True,
         audio_language : str = "en",
         chunk_size : int = 1000,
         chunk_overlap : int = 100,

         ) -> UnifiedDocument:
        """
        Transcribe audio file asynchronously.
        
        Uses async file operations to avoid blocking the event loop.
        """
        audio_path = Path(audio_path)
        
        # Async file validation
        if not await _async_file_exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if not await _async_is_file(audio_path):
            raise IsADirectoryError(f"Audio file is a directory: {audio_path}")
        if not audio_path.suffix.lower() in self.supported_formats:
            raise ValueError(f"Unsupported audio format: {audio_path.suffix}")
        
        logger.info(f"Transcribing audio from: {audio_path}")

        try:
            config = aai.TranscriptionConfig(
                speaker_labels=enable_speaker_diarization,
                punctuate=enable_auto_punctuation,  
                language_code=audio_language,
                format_text=True
            )
            logger.info(f"Transcribing audio with config: {config}")
            
            # Run transcription in thread pool to avoid blocking
            transcriber = aai.Transcriber(config=config)
            transcript = await asyncio.to_thread(transcriber.transcribe, str(audio_path))
            
            if hasattr(transcript, 'error') and transcript.error:
                raise TranscriptionError(f"Transcription failed: {transcript.error}")
            
            logger.info(f"Transcription completed successfully")
            return await self._process_transcript(transcript, str(audio_path), chunk_size, chunk_overlap)
        except Exception as e:
            logger.error(f"Failed to transcribe audio: {e}", exc_info=True)
            raise TranscriptionError(f"Failed to transcribe audio: {e}")
    
    async def _process_transcript(
        self,
        transcript: aai.Transcript,
        source_file: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
    ) -> UnifiedDocument:
        try:
            logger.info(f"Processing transcript from: {source_file}")
            transcript_metadata = {}
            
            transcript_metadata["duration"] = safe_getattr(transcript, 'audio_duration')
            transcript_metadata["confidence"] = safe_getattr(transcript, 'confidence')
            transcript_metadata["language"] = safe_getattr(transcript, 'language_code')
            transcript_metadata["audio_url"] = safe_getattr(transcript, 'audio_url')
            transcript_metadata["transcript_id"] = safe_getattr(transcript, 'id')
            utterances = safe_getattr(transcript, 'utterances')
            transcript_text = safe_getattr(transcript, 'text')
            
            if utterances:
                logger.info(f"Creating chunks with speakers from {len(utterances)} utterances")
                doc = self._create_chunks_with_speakers(
                    utterances,
                    source_file,
                    chunk_size,
                    chunk_overlap,
                    transcript_metadata
                )
            elif transcript_text:
                logger.warning("No utterances found in transcript, using text")
                doc = self._create_chunks_without_speakers(
                    transcript_text,
                    source_file,
                    chunk_size,
                    chunk_overlap,
                    transcript_metadata
                )
            else:
                raise TranscriptionError("Transcript has no text or utterances available")
            
            logger.info(f"Created {doc.chunk_count} chunks from transcript")
            return doc
        except Exception as e:
            logger.error(f"Failed to process transcript: {e}", exc_info=True)
            raise TranscriptionError(f"Failed to process transcript: {e}")
    
    def _create_chunks_with_speakers(self, 
    utterances: List[aai.Utterance],
    source_file: str,
    chunk_size: int,
    chunk_overlap: int,
    transcript_metadata: Dict[str, Any]) -> UnifiedDocument:
        """
        Create a UnifiedDocument with DocumentChunk objects from speaker utterances.
        
        Returns:
            UnifiedDocument with chunks containing speaker segments
        """
        doc = UnifiedDocument(
            id=uuid.uuid4(),
            user_id=get_settings().anonymous_user_id,
            filename=Path(source_file).name,
            source_type=DocumentType.AUDIO,
            status=ProcessingStatus.COMPLETED,
            storage_path=source_file,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            metadata=transcript_metadata
        )
        
        # Convert utterances to speaker segments
        segments = []
        for u in utterances:
            segment = SpeakerSegment(
                speaker=u.speaker,
                start_time=u.start,
                end_time=u.end,
                text=u.text,
                confidence=getattr(u, 'confidence', 0.0)
            )
            segments.append(segment)
        
        # Group segments into chunks
        current_chunk_segments = []
        current_chunk_text = []
        current_chunk_start = None
        current_chunk_end = None
        chunk_index = 0
        
        for segment in segments:
            # Start a new chunk if needed
            if not current_chunk_segments:
                current_chunk_segments = [segment]
                current_chunk_text = [f"[{segment.speaker}] {segment.text}"]
                current_chunk_start = segment.start_time
                current_chunk_end = segment.end_time
            else:
                # Check if adding this segment would exceed chunk size
                potential_text = " ".join(current_chunk_text + [f"[{segment.speaker}] {segment.text}"])
                
                if len(potential_text) > chunk_size:
                    # Save current chunk and start new one
                    chunk_text = "\n".join(current_chunk_text)
                    doc.add_chunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        metadata={
                            "start_time": current_chunk_start,
                            "end_time": current_chunk_end,
                            "speakers": list(set(s.speaker for s in current_chunk_segments)),
                            "segment_count": len(current_chunk_segments)
                        }
                    )
                    chunk_index += 1
                    
                    # Start new chunk with overlap
                    # Include last few segments for context (overlap)
                    overlap_segments = current_chunk_segments[-2:] if len(current_chunk_segments) >= 2 else []
                    current_chunk_segments = overlap_segments + [segment]
                    current_chunk_text = [f"[{s.speaker}] {s.text}" for s in current_chunk_segments]
                    current_chunk_start = overlap_segments[0].start_time if overlap_segments else segment.start_time
                    current_chunk_end = segment.end_time
                else:
                    # Add to current chunk
                    current_chunk_segments.append(segment)
                    current_chunk_text.append(f"[{segment.speaker}] {segment.text}")
                    current_chunk_end = segment.end_time
        
        # Don't forget the last chunk
        if current_chunk_segments:
            chunk_text = "\n".join(current_chunk_text)
            doc.add_chunk(
                content=chunk_text,
                chunk_index=chunk_index,
                metadata={
                    "start_time": current_chunk_start,
                    "end_time": current_chunk_end,
                    "speakers": list(set(s.speaker for s in current_chunk_segments)),
                    "segment_count": len(current_chunk_segments)
                }
            )
        
        return doc
    
    def _create_chunks_without_speakers(
        self,
        transcript_text: str,
        source_file: str,
        chunk_size: int,
        chunk_overlap: int,
        transcript_metadata: Dict[str, Any]
    ) -> UnifiedDocument:
        """
        Create a UnifiedDocument with DocumentChunk objects from plain transcript text.
        
        Returns:
            UnifiedDocument with chunks
        """
        doc = UnifiedDocument(
            id=uuid.uuid4(),
            user_id=get_settings().anonymous_user_id,
            filename=Path(source_file).name,
            source_type=DocumentType.AUDIO,
            status=ProcessingStatus.COMPLETED,
            storage_path=source_file,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            metadata=transcript_metadata
        )
        
        # Use the chunk_manager to create chunks
        chunks = chunk_text(transcript_text, chunk_size, chunk_overlap)
        
        for i, chunk_text_content in enumerate(chunks):
            doc.add_chunk(
                content=chunk_text_content,
                chunk_index=i,
                metadata={
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
            )
        
        return doc


def safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get an attribute from an object, returning default if not found."""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default
