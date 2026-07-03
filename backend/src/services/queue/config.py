from pydantic import BaseModel, Field
from typing import Dict


class QueueSettings(BaseModel):
    """Configuration for Procrastinate queue workers."""

    # Worker Concurrency (per priority queue)
    workers_critical: int = Field(
        default=1,
        description="Workers for critical queue (audio, YouTube, large documents)",
    )
    workers_high: int = Field(
        default=1, description="Workers for high priority queue (podcast generation)"
    )
    workers_standard: int = Field(
        default=1, description="Workers for standard queue (quiz, flashcard, mindmap)"
    )

    # Retry Policies (based on failure rates)
    retry_attempts_critical: int = Field(
        default=3, description="Retry count for critical tasks (10-20% failure rate)"
    )
    retry_attempts_high: int = Field(
        default=2,
        description="Retry count for high priority tasks (10-15% failure rate)",
    )
    retry_attempts_standard: int = Field(
        default=2, description="Retry count for standard tasks (5-6% failure rate)"
    )

    # Timeout Limits (in seconds)
    timeout_critical: int = Field(
        default=900,  # 15 minutes
        description="Max execution time for critical tasks (audio transcription: 3-10min)",
    )
    timeout_high: int = Field(
        default=1800,  # 30 minutes
        description="Max execution time for high priority tasks (podcast: 5-25min)",
    )
    timeout_standard: int = Field(
        default=120,  # 2 minutes
        description="Max execution time for standard tasks (quiz: 20-45s)",
    )

    # Dead Job Recovery
    enable_dead_job_recovery: bool = Field(
        default=True,
        description="Reset stuck 'PROCESSING' jobs to 'FAILED' on worker startup",
    )
    dead_job_threshold_minutes: int = Field(
        default=30,
        description="Jobs stuck in 'PROCESSING' for this long are considered dead",
    )


# Default queue settings instance
queue_settings = QueueSettings()


# Task retry configuration mapping
TASK_RETRY_CONFIG: Dict[str, Dict[str, int]] = {
    "critical": {
        "retry_attempts": queue_settings.retry_attempts_critical,
        "timeout_seconds": queue_settings.timeout_critical,
    },
    "high": {
        "retry_attempts": queue_settings.retry_attempts_high,
        "timeout_seconds": queue_settings.timeout_high,
    },
    "standard": {
        "retry_attempts": queue_settings.retry_attempts_standard,
        "timeout_seconds": queue_settings.timeout_standard,
    },
}


__all__ = ["QueueSettings", "queue_settings", "TASK_RETRY_CONFIG"]
