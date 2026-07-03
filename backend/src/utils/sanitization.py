"""
Input sanitization and validation utilities.
Prevents prompt injection, XSS, and other injection attacks.
"""

import re
import html
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


class ContentType(Enum):
    """Content types for validation."""
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"
    CODE = "code"


@dataclass
class SanitizationConfig:
    """Configuration for input sanitization."""
    max_length: int = 10000
    allow_html: bool = False
    allow_markdown: bool = True
    strip_null_bytes: bool = True
    normalize_whitespace: bool = True
    block_prompt_injection: bool = True


class InputSanitizer:
    """
    Sanitizes user inputs before processing.

    Protects against:
    - Prompt injection attacks
    - XSS attempts
    - Null byte injection
    - Excessive length attacks
    """

    # Patterns that indicate prompt injection attempts
    PROMPT_INJECTION_PATTERNS = [
        r'ignore\s+(previous|above|earlier)',
        r'forget\s+(previous|above|earlier)',
        r'system\s*:\s*',
        r'user\s*:\s*',
        r'assistant\s*:\s*',
        r'\[\s*system\s*\]',
        r'\[\s*instruction\s*\]',
        r'\[\s*prompt\s*\]',
        r'<\s*system\s*>',
        r'<\s*instruction\s*>',
        r'new\s+instructions?\s*:',
        r'override\s+instructions?',
    ]

    # Dangerous HTML tags to remove
    DANGEROUS_HTML_TAGS = [
        'script', 'iframe', 'object', 'embed', 'form',
        'input', 'textarea', 'button', 'link', 'style'
    ]

    def __init__(self, config: Optional[SanitizationConfig] = None):
        self.config = config or SanitizationConfig()
        self._injection_regex = re.compile(
            '|'.join(self.PROMPT_INJECTION_PATTERNS),
            re.IGNORECASE
        )

    def sanitize(
        self,
        text: str,
        content_type: ContentType = ContentType.TEXT
    ) -> str:
        """
        Sanitize input text.

        Args:
            text: Raw input text
            content_type: Expected content type

        Returns:
            Sanitized text

        Raises:
            ValidationError: If input is invalid or suspicious
        """
        if not isinstance(text, str):
            raise ValidationError("Input must be a string")

        # Check length
        if len(text) > self.config.max_length:
            raise ValidationError(
                f"Input too long: {len(text)} characters (max {self.config.max_length})"
            )

        # Remove null bytes
        if self.config.strip_null_bytes:
            text = text.replace('\x00', '')

        # Check for prompt injection
        if self.config.block_prompt_injection:
            if self._detect_prompt_injection(text):
                raise ValidationError(
                    "Potential prompt injection detected. "
                    "Please rephrase your input."
                )

        # Content-type specific sanitization
        if content_type == ContentType.TEXT:
            text = self._sanitize_text(text)
        elif content_type == ContentType.HTML:
            text = self._sanitize_html(text)
        elif content_type == ContentType.MARKDOWN:
            text = self._sanitize_markdown(text)

        # Normalize whitespace
        if self.config.normalize_whitespace:
            text = self._normalize_whitespace(text)

        return text

    def _detect_prompt_injection(self, text: str) -> bool:
        """Detect potential prompt injection attempts."""
        return bool(self._injection_regex.search(text))

    def _sanitize_text(self, text: str) -> str:
        """Sanitize plain text input."""
        # Escape HTML entities to prevent XSS
        if not self.config.allow_html:
            text = html.escape(text)
        return text

    def _sanitize_html(self, text: str) -> str:
        """Sanitize HTML content."""
        # Remove dangerous tags
        for tag in self.DANGEROUS_HTML_TAGS:
            pattern = f'<{tag}[^>]*>.*?</{tag}>|<{tag}[^>]*/?>'
            text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
        return text

    def _sanitize_markdown(self, text: str) -> str:
        """Sanitize markdown content."""
        # Allow most markdown but escape raw HTML
        if not self.config.allow_html:
            # Simple HTML tag removal (not perfect but catches obvious cases)
            text = re.sub(r'<[^>]+>', '', text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace characters."""
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        # Replace multiple newlines with double newline
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


class LLMInputValidator:
    """
    Validates inputs specifically for LLM processing.

    Ensures inputs are safe and appropriate for the LLM context.
    """

    # Maximum tokens (rough estimate)
    MAX_INPUT_TOKENS = 4000

    # Suspicious patterns for LLM inputs
    SUSPICIOUS_PATTERNS = [
        r'\{\{\s*\.\w+\s*\}\}',  # Template injection
        r'\$\{\s*\w+\s*\}',       # Shell variable expansion
        r'`[^`]*`',                # Command substitution (backticks)
        r'\$\([^)]*\)',            # Command substitution $()
    ]

    def __init__(self):
        self._suspicious_regex = re.compile(
            '|'.join(self.SUSPICIOUS_PATTERNS),
            re.IGNORECASE
        )

    def validate_query(self, query: str) -> str:
        """
        Validate and sanitize a user query for LLM processing.

        Args:
            query: User query string

        Returns:
            Validated query

        Raises:
            ValidationError: If query is invalid
        """
        if not query or not query.strip():
            raise ValidationError("Query cannot be empty")

        # Check for suspicious patterns
        if self._suspicious_regex.search(query):
            raise ValidationError(
                "Query contains potentially dangerous patterns. "
                "Please remove special characters like backticks or template syntax."
            )

        # Rough token estimation (1 token ≈ 4 characters)
        estimated_tokens = len(query) / 4
        if estimated_tokens > self.MAX_INPUT_TOKENS:
            raise ValidationError(
                f"Query too long: ~{int(estimated_tokens)} tokens (max {self.MAX_INPUT_TOKENS})"
            )

        return query.strip()

    def validate_context(self, context: str) -> str:
        """Validate context/document content."""
        # Context can be longer but still needs limits
        if len(context) > 100000:  # ~25k tokens
            raise ValidationError("Context too large for processing")

        return context


# Global sanitizer instance
default_sanitizer = InputSanitizer()
llm_validator = LLMInputValidator()


def sanitize_for_llm(text: str) -> str:
    """Convenience function for LLM input sanitization."""
    sanitized = default_sanitizer.sanitize(text)
    return llm_validator.validate_query(sanitized)

