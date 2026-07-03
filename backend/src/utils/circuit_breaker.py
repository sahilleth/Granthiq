from enum import Enum
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable, Optional, Tuple, Type
from loguru import logger
import asyncio


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"         # Normal operation, requests allowed
    OPEN = "open"             # Failing, reject all requests
    HALF_OPEN = "half_open"   # Testing if service recovered


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    def __init__(self, service_name: str, recovery_time: datetime):
        self.service_name = service_name
        self.recovery_time = recovery_time
        super().__init__(
            f"Circuit breaker OPEN for {service_name}. "
            f"Service will be retried after {recovery_time.isoformat()}"
        )


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service failing, reject requests immediately
    - HALF_OPEN: Testing recovery, allow one test request

    Example:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        @breaker.call
        async def risky_operation():
            # If this fails 5 times, circuit opens for 60 seconds
            return await external_service.call()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        success_threshold: int = 2,
        name: Optional[str] = None
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying again (OPEN → HALF_OPEN)
            expected_exceptions: Exceptions that trigger circuit breaker
            success_threshold: Consecutive successes needed in HALF_OPEN to close
            name: Optional name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self.success_threshold = success_threshold
        self.name = name or "unnamed"

        # State tracking
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED

        # Statistics
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.circuit_open_count = 0

        # Thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"Circuit breaker '{self.name}' initialized: "
            f"threshold={failure_threshold}, timeout={recovery_timeout}s"
        )

    def call(self, func: Callable):
        """
        Decorator to wrap async functions with circuit breaker.

        Usage:
            @breaker.call
            async def my_function():
                pass
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with self._lock:
                self.total_calls += 1

                # Check if circuit is open
                if self.state == CircuitState.OPEN:
                    if self._should_attempt_reset():
                        logger.info(f"Circuit breaker '{self.name}': Attempting recovery (OPEN → HALF_OPEN)")
                        self.state = CircuitState.HALF_OPEN
                        self.success_count = 0
                    else:
                        # Circuit still open, reject immediately
                        recovery_time = self.last_failure_time + timedelta(seconds=self.recovery_timeout)
                        logger.warning(
                            f"Circuit breaker '{self.name}': OPEN - rejecting request "
                            f"(recovery at {recovery_time.isoformat()})"
                        )
                        raise CircuitBreakerError(self.name, recovery_time)

            # Try to execute the function
            try:
                result = await func(*args, **kwargs)
                await self._on_success()
                return result

            except self.expected_exceptions as e:
                await self._on_failure(e)
                raise

        return wrapper

    async def _on_success(self):
        """Handle successful execution."""
        async with self._lock:
            self.total_successes += 1

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.info(
                    f"Circuit breaker '{self.name}': Success in HALF_OPEN state "
                    f"({self.success_count}/{self.success_threshold})"
                )

                if self.success_count >= self.success_threshold:
                    logger.info(f"Circuit breaker '{self.name}': Recovery successful (HALF_OPEN → CLOSED)")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0

            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                if self.failure_count > 0:
                    logger.debug(f"Circuit breaker '{self.name}': Resetting failure count (was {self.failure_count})")
                    self.failure_count = 0

    async def _on_failure(self, exception: Exception):
        """Handle failed execution."""
        async with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            logger.warning(
                f"Circuit breaker '{self.name}': Failure {self.failure_count}/{self.failure_threshold} "
                f"(exception: {type(exception).__name__})"
            )

            if self.state == CircuitState.HALF_OPEN:
                # Failed during recovery attempt, go back to OPEN
                logger.error(
                    f"Circuit breaker '{self.name}': Recovery failed, reopening circuit (HALF_OPEN → OPEN)"
                )
                self.state = CircuitState.OPEN
                self.circuit_open_count += 1
                self.failure_count = self.failure_threshold  # Keep circuit open

            elif self.failure_count >= self.failure_threshold:
                # Too many failures, open the circuit
                logger.error(
                    f"Circuit breaker '{self.name}': Threshold reached, opening circuit (CLOSED → OPEN). "
                    f"Will retry after {self.recovery_timeout}s"
                )
                self.state = CircuitState.OPEN
                self.circuit_open_count += 1

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return False

        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure >= timedelta(seconds=self.recovery_timeout)

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "current_failure_count": self.failure_count,
            "circuit_opened_times": self.circuit_open_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "failure_rate": (
                round(self.total_failures / self.total_calls * 100, 2)
                if self.total_calls > 0 else 0
            )
        }

    def reset(self):
        """Manually reset circuit breaker (for testing or manual recovery)."""
        logger.info(f"Circuit breaker '{self.name}': Manual reset")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None


# Global circuit breaker instances for common services
# These can be imported and used throughout the application

llm_circuit_breaker = CircuitBreaker(
    name="llm_service",
    failure_threshold=5,
    recovery_timeout=60,
    expected_exceptions=(Exception,)  # Catch all LLM-related errors
)

storage_circuit_breaker = CircuitBreaker(
    name="storage_service",
    failure_threshold=3,
    recovery_timeout=30,
    expected_exceptions=(Exception,)  # Catch storage errors
)

vector_db_circuit_breaker = CircuitBreaker(
    name="vector_database",
    failure_threshold=3,
    recovery_timeout=30,
    expected_exceptions=(Exception,)  # Catch Qdrant errors
)

external_api_circuit_breaker = CircuitBreaker(
    name="external_api",
    failure_threshold=5,
    recovery_timeout=60,
    expected_exceptions=(Exception,)  # Catch external API errors
)
