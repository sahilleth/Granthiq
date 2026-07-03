"""
Unit tests for LLM provider selector.
Tests provider selection logic for chat and generation services.
"""

import pytest
from unittest.mock import Mock, patch

from src.services.llm.provider_selector import (
    select_chat_llm_provider,
    select_generation_llm_provider,
)


class TestSelectChatLLMProvider:
    """Test suite for select_chat_llm_provider function."""

    def test_select_chat_with_groq_api_key(self):
        """Test that Groq is selected when API key is available."""
        settings = Mock()
        settings.llm.provider = "gemini"
        settings.llm.groq_api_key = "gsk_test_key"

        result = select_chat_llm_provider(settings)

        assert result == "groq"

    def test_select_chat_without_groq_uses_configured(self):
        """Test that configured provider is used when Groq key is missing."""
        settings = Mock()
        settings.llm.provider = "openai"
        settings.llm.groq_api_key = None

        result = select_chat_llm_provider(settings)

        assert result is None  # Returns None to use configured provider

    def test_select_chat_gemini_configured_no_groq(self):
        """Test that Gemini is used when configured and Groq unavailable."""
        settings = Mock()
        settings.llm.provider = "gemini"
        settings.llm.model_name = "gemini-2.5-flash"
        settings.llm.groq_api_key = None

        result = select_chat_llm_provider(settings)

        assert result is None


class TestSelectGenerationLLMProvider:
    """Test suite for select_generation_llm_provider function."""

    def test_select_generation_groq_priority(self):
        """Test that Groq is prioritized for generation when available."""
        settings = Mock()
        settings.llm.groq_api_key = "gsk_test_key"
        settings.llm.gemini_api_key = "gemini_test_key"
        settings.llm.provider = "gemini"
        settings.llm.model_name = "gemini-2.5-flash"

        provider, model_name, api_key = select_generation_llm_provider(settings)

        assert provider == "groq"
        assert api_key == "gsk_test_key"
        assert "llama" in model_name

    def test_select_generation_fallback_to_gemini(self):
        """Test that Gemini is used when Groq is unavailable."""
        settings = Mock()
        settings.llm.groq_api_key = None
        settings.llm.gemini_api_key = "gemini_test_key"
        settings.llm.provider = "gemini"
        settings.llm.model_name = "gemini-2.5-flash"

        provider, model_name, api_key = select_generation_llm_provider(settings)

        assert provider == "gemini"
        assert api_key == "gemini_test_key"
        assert model_name == "gemini-2.5-flash"

    def test_select_generation_fallback_to_configured(self):
        """Test that configured provider is used when no preferred keys available."""
        settings = Mock()
        settings.llm.groq_api_key = None
        settings.llm.gemini_api_key = None
        settings.llm.provider = "openai"
        settings.llm.model_name = "gpt-4"
        settings.llm.openai_api_key = "openai_test_key"

        provider, model_name, api_key = select_generation_llm_provider(settings)

        assert provider == "openai"
        assert api_key == "openai_test_key"
        assert model_name == "gpt-4"

    def test_select_generation_with_none_settings(self):
        """Test that function works with None settings (uses get_settings)."""
        with patch('src.services.llm.provider_selector.get_settings') as mock_get_settings:
            mock_settings = Mock()
            mock_settings.llm.groq_api_key = "gsk_test"
            mock_settings.llm.gemini_api_key = None
            mock_settings.llm.provider = "gemini"
            mock_settings.llm.model_name = "gemini-2.5-flash"
            mock_get_settings.return_value = mock_settings

            provider, model_name, api_key = select_generation_llm_provider(None)

            assert provider == "groq"
            mock_get_settings.assert_called_once()
