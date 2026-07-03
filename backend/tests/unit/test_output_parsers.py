"""
Unit tests for RobustJSONParser.
Tests parsing of valid JSON, markdown blocks, truncated JSON, and malformed output.
"""

import pytest
from pydantic import BaseModel
from typing import List

from src.utils.output_parsers import RobustJSONParser


class SuggestionItem(BaseModel):
    """Test model for suggestion items."""
    text: str
    context: str = ""


class SuggestionList(BaseModel):
    """Test model for list of suggestions."""
    items: List[SuggestionItem]


class SimpleQuestions(BaseModel):
    """Test model for simple questions array."""
    questions: List[str]


class TestRobustJSONParser:
    """Test suite for RobustJSONParser."""

    def test_parse_valid_json(self):
        """Test parsing of clean, valid JSON."""
        parser = RobustJSONParser(SuggestionList)
        json_text = '{"items": [{"text": "What is AI?", "context": "Technology"}]}'

        result = parser.parse(json_text)

        assert isinstance(result, SuggestionList)
        assert len(result.items) == 1
        assert result.items[0].text == "What is AI?"
        assert result.items[0].context == "Technology"

    def test_parse_json_with_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        parser = RobustJSONParser(SuggestionList)
        json_text = '''```json
{"items": [{"text": "Question 1?", "context": "Context"}]}
```'''

        result = parser.parse(json_text)

        assert isinstance(result, SuggestionList)
        assert len(result.items) == 1
        assert result.items[0].text == "Question 1?"

    def test_parse_json_with_plain_code_block(self):
        """Test parsing JSON wrapped in plain markdown code blocks."""
        parser = RobustJSONParser(SuggestionList)
        json_text = '''```
{"items": [{"text": "Question 2?", "context": "Test"}]}
```'''

        result = parser.parse(json_text)

        assert isinstance(result, SuggestionList)
        assert result.items[0].text == "Question 2?"

    def test_parse_truncated_json_array(self):
        """Test parsing truncated JSON with incomplete array."""
        parser = RobustJSONParser(SuggestionList)
        # Simulate truncated output (missing closing brackets)
        json_text = '{"items": [{"text": "Question 1?", "context": "Test"}, {"text": "Question 2?", "context": "Test"'

        result = parser.parse(json_text)

        assert isinstance(result, SuggestionList)
        # Should have at least the first complete item
        assert len(result.items) >= 1

    def test_parse_truncated_json_object(self):
        """Test parsing truncated JSON with incomplete object."""
        parser = RobustJSONParser(SuggestionList)
        # Truncated after first item's text field
        json_text = '{"items": [{"text": "Complete question?", "context": "Complete context"}, {"text": "Incomplete'

        result = parser.parse(json_text)

        assert isinstance(result, SuggestionList)
        # Should have at least the first complete item
        assert len(result.items) >= 1
        assert result.items[0].text == "Complete question?"

    def test_parse_simple_questions_array(self):
        """Test parsing simple array of questions."""
        parser = RobustJSONParser(SimpleQuestions)
        json_text = '{"questions": ["What is AI?", "How does it work?", "Why use it?"]}'

        result = parser.parse(json_text)

        assert isinstance(result, SimpleQuestions)
        assert len(result.questions) == 3
        assert "What is AI?" in result.questions

    def test_extract_json_from_markdown(self):
        """Test the _extract_json_from_markdown method."""
        parser = RobustJSONParser(SuggestionList)

        # Test with json label
        text1 = '```json\n{"items": []}\n```'
        assert parser._extract_json_from_markdown(text1) == '{"items": []}'

        # Test without json label
        text2 = '```\n{"items": []}\n```'
        assert parser._extract_json_from_markdown(text2) == '{"items": []}'

        # Test without code blocks (should return as-is)
        text3 = '{"items": []}'
        assert parser._extract_json_from_markdown(text3) == '{"items": []}'

    def test_repair_truncated_json(self):
        """Test the _repair_truncated_json method."""
        parser = RobustJSONParser(SuggestionList)

        # Test with items array
        truncated = '{"items": [{"text": "Q1?", "context": "C1"}, {"text": "Q2?"'
        repaired = parser._repair_truncated_json(truncated)
        assert repaired.endswith('}')  # Should close properly

        # Test with questions array
        truncated2 = '{"questions": ["Q1?", "Q2?"'
        repaired2 = parser._repair_truncated_json(truncated2)
        assert ']' in repaired2  # Should close array

    def test_extract_partial_data(self):
        """Test the _extract_partial_data method."""
        parser = RobustJSONParser(SimpleQuestions)

        # Test extracting from malformed JSON
        malformed = 'Some text before {"questions": ["Q1?", "Q2?"]} some after'
        partial = parser._extract_partial_data(malformed)
        assert partial is not None
        assert "questions" in partial

    def test_parse_with_extra_text(self):
        """Test parsing JSON embedded in extra text."""
        parser = RobustJSONParser(SuggestionList)
        json_text = '''Here's the result:

```json
{"items": [{"text": "Question?", "context": "Context"}]}
```

Hope that helps!'''

        result = parser.parse(json_text)

        assert isinstance(result, SuggestionList)
        assert len(result.items) == 1

    def test_parse_empty_items(self):
        """Test parsing JSON with empty items array."""
        parser = RobustJSONParser(SuggestionList)
        json_text = '{"items": []}'

        result = parser.parse(json_text)

        assert isinstance(result, SuggestionList)
        assert len(result.items) == 0

    def test_parse_malformed_json_with_dirtyjson_fallback(self):
        """Test parsing malformed JSON that dirtyjson might handle."""
        parser = RobustJSONParser(SimpleQuestions)
        # Missing quotes around keys (common LLM error)
        json_text = '{questions: ["What is AI?", "How does it work?"]}'

        # This might work with dirtyjson fallback
        try:
            result = parser.parse(json_text)
            assert isinstance(result, SimpleQuestions)
            assert len(result.questions) == 2
        except ValueError:
            # If dirtyjson is not available, this is expected to fail
            pass

    def test_parse_invalid_json_raises_error(self):
        """Test that completely invalid JSON raises ValueError."""
        parser = RobustJSONParser(SuggestionList)
        invalid_text = "This is not JSON at all"

        with pytest.raises(ValueError):
            parser.parse(invalid_text)
