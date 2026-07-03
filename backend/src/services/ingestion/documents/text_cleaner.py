
from typing import Optional
from unstructured.cleaners.core import (
    clean,
    clean_bullets,
    clean_dashes,
    clean_non_ascii_chars,
    clean_ordered_bullets,
    clean_trailing_punctuation,
    group_broken_paragraphs,
    replace_unicode_quotes,
    bytes_string_to_string,
)
from loguru import logger


def clean_text_for_chunking(
    text: str,
    remove_bullets: bool = True,
    remove_dashes: bool = True,
    group_paragraphs: bool = True,
    remove_trailing_punct: bool = False,  # Keep trailing punctuation for context
    lowercase: bool = False,  # Keep original case for better embeddings
) -> str:
    """
    Clean text using Unstructured cleaning functions.
    
    Args:
        text: Raw text to clean
        remove_bullets: Remove bullet points
        remove_dashes: Remove dashes
        group_paragraphs: Group broken paragraphs (important for PDFs)
        remove_trailing_punct: Remove trailing punctuation
        lowercase: Lowercase text (usually False for better embeddings)
    
    Returns:
        Cleaned text
    """
    if not text or not text.strip():
        return text
    
    try:
        # Only convert byte strings if the text actually looks like a byte string representation
        # Check if text contains patterns like \x9f, \x80, etc. (byte escape sequences)
        if isinstance(text, str) and ('\\x' in text or '\\u' in text):
            try:
                # Only call bytes_string_to_string if it looks like a byte string
                # This function expects strings like "Hello ð\x9f\x98\x80"
                text = bytes_string_to_string(text, encoding="utf-8")
            except (ValueError, UnicodeDecodeError, TypeError) as e:
                # If it fails, it's probably already a proper string, just continue
                logger.debug(f"bytes_string_to_string failed (text is likely already decoded): {e}")
                pass
        
        # Replace unicode quotes
        try:
            text = replace_unicode_quotes(text)
        except Exception as e:
            logger.debug(f"replace_unicode_quotes failed: {e}")
            pass
        
        # Group broken paragraphs (very important for PDFs)
        if group_paragraphs:
            try:
                text = group_broken_paragraphs(text)
            except Exception as e:
                logger.debug(f"group_broken_paragraphs failed: {e}")
                pass
        
        # Apply comprehensive cleaning
        try:
            text = clean(
                text,
                bullets=remove_bullets,
                dashes=remove_dashes,
                extra_whitespace=True,  # Always remove extra whitespace
                trailing_punctuation=remove_trailing_punct,
                lowercase=lowercase,
            )
        except Exception as e:
            logger.debug(f"clean function failed: {e}")
            pass
        
        # Remove non-ASCII characters that might cause issues
        # (but keep common ones like quotes, dashes that were already handled)
        # Skip this step as it's too aggressive and removes valid unicode characters
        # text = clean_non_ascii_chars(text)
        
        return text.strip()
    except Exception as e:
        # If any critical error occurs, return original text
        logger.debug(f"Error cleaning text: {e}. Returning original text.")
        return text.strip() if isinstance(text, str) else str(text).strip()


def clean_element_text(element) -> str:
    """
    Clean text from an Unstructured element.
    
    Args:
        element: Unstructured element with .text attribute
    
    Returns:
        Cleaned text
    """
    if not hasattr(element, 'text') or not element.text:
        return ""
    
    return clean_text_for_chunking(element.text)

