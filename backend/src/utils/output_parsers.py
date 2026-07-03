"""Robust output parsers for handling LLM responses."""
from typing import Any, Optional
from llama_index.core.output_parsers import PydanticOutputParser
import re
import json
from loguru import logger


class RobustJSONParser(PydanticOutputParser):
    """
    Robustly parses JSON from LLM output.
    Handles markdown code blocks, repairs truncated JSON, and uses dirtyjson as fallback.
    """

    def parse(self, text: str) -> Any:
        """
        Parse text into Pydantic model with multiple fallback strategies.

        Strategy:
        1. Strip markdown code blocks
        2. Try standard Pydantic parse
        3. Try JSON repair for truncated output
        4. Try dirtyjson as lenient fallback
        5. Return partial data if possible, otherwise raise
        """
        original_text = text
        clean_text = text.strip()

        # 1. Strip Markdown Code Blocks (handles both complete and truncated blocks)
        clean_text = self._extract_json_from_markdown(clean_text)

        # 2. Attempt Standard Parse
        try:
            return super().parse(clean_text)
        except Exception as e:
            logger.debug(f"Standard parse failed: {e}")

        # 3. Repair truncated JSON
        repaired_text = self._repair_truncated_json(clean_text)

        try:
            return super().parse(repaired_text)
        except Exception as e:
            logger.debug(f"Repaired parse failed: {e}")

        # 4. Try dirtyjson as lenient fallback (handles malformed JSON)
        try:
            dirty_parsed = self._try_dirtyjson_parse(repaired_text)
            if dirty_parsed is not None:
                # Validate against pydantic model
                return self._output_type(**dirty_parsed)
        except Exception as e:
            logger.debug(f"DirtyJSON parse failed: {e}")

        # 5. Last resort: try to extract partial data
        try:
            partial_data = self._extract_partial_data(repaired_text)
            if partial_data is not None:
                logger.warning(f"Using partial data extraction due to parse failures")
                return self._output_type(**partial_data)
        except Exception as e:
            logger.debug(f"Partial extraction failed: {e}")

        # All strategies failed - log and raise
        logger.error(f"Fatal parsing error. Raw text: {original_text[:500]}...")
        raise ValueError(
            f"Failed to parse LLM output after all recovery attempts. "
            f"Original error: {str(e)[:100]}"
        )

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON content from markdown code blocks."""
        if "```" not in text:
            return text

        # First try complete code blocks with closing ```
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Handle truncated code blocks (opening ``` without closing ```)
        truncated_pattern = r"```(?:json)?\s*(.*)"
        truncated_match = re.search(truncated_pattern, text, re.DOTALL)
        if truncated_match:
            return truncated_match.group(1).strip()

        return text

    def _try_dirtyjson_parse(self, text: str) -> Optional[dict]:
        """
        Use dirtyjson as a lenient JSON parser fallback.
        dirtyjson can handle common JSON syntax errors.
        """
        try:
            import dirtyjson
            return dirtyjson.loads(text)
        except ImportError:
            logger.debug("dirtyjson not available for fallback parsing")
            return None
        except Exception as e:
            logger.debug(f"dirtyjson parsing failed: {e}")
            return None

    def _extract_partial_data(self, text: str) -> Optional[dict]:
        """
        Extract partial data from malformed JSON as last resort.
        Attempts to find key-value pairs even in broken JSON.
        """
        try:
            # Try to find array items or object properties
            # Pattern for "key": "value" pairs
            pairs = re.findall(r'"(\w+)":\s*"([^"]*)"', text)
            if pairs:
                return dict(pairs)

            # Pattern for array of strings (common for suggestions)
            strings = re.findall(r'"([^"]+)"', text)
            if strings:
                # Check if this looks like a questions/items array
                if any(keyword in text.lower() for keyword in ['questions', 'items', 'suggestions']):
                    return {"questions": strings} if "questions" in text.lower() else {"items": [{"text": s} for s in strings]}

            return None
        except Exception as e:
            logger.debug(f"Partial extraction error: {e}")
            return None

    def _repair_truncated_json(self, text: str) -> str:
        """Attempt to repair truncated JSON by cutting incomplete parts and closing."""
        # If it's an object with items array that got cut off
        if '"items"' in text or '"questions"' in text:
            # Try multiple strategies to find the last complete item

            # Strategy 1: Find the last complete object ending with "},"
            # This captures items in an array like {"text": "...", "context": "..."},
            last_complete_item = max(
                text.rfind('"},'),
                text.rfind('"}')
            )

            # Strategy 2: If we have a partial string value, find the last complete one
            # Look for patterns like "key": "value" that are complete
            if last_complete_item == -1:
                # Find any complete quoted string
                last_quote_pair = -1
                in_string = False
                escape_next = False
                for i, char in enumerate(text):
                    if escape_next:
                        escape_next = False
                        continue
                    if char == '\\':
                        escape_next = True
                        continue
                    if char == '"':
                        if in_string:
                            last_quote_pair = i
                        in_string = not in_string
                last_complete_item = last_quote_pair

            if last_complete_item != -1:
                # Cut at last complete point
                text = text[:last_complete_item + 1]

                # Remove trailing comma if present
                text = text.rstrip().rstrip(',')

                # Count what needs closing
                open_braces = text.count("{") - text.count("}")
                open_brackets = text.count("[") - text.count("]")

                # Close any open structures
                text += "}" * max(0, open_braces)
                # Make sure brackets close after braces for arrays
                if open_brackets > 0 and open_braces <= 0:
                    text += "]" * open_brackets
                elif open_brackets > 0:
                    # We closed braces, now we might need to close brackets
                    remaining_brackets = text.count("[") - text.count("]")
                    text += "]" * max(0, remaining_brackets)

        return text
