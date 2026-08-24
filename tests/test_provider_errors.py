from __future__ import annotations

import pytest

from integrations.ai_client import OpenAIProvider, build_ai_provider


def test_openai_provider_requires_key(runtime_config) -> None:
    with pytest.raises(Exception, match="OPENAI_API_KEY"):
        OpenAIProvider(runtime_config)


def test_unknown_ai_provider(runtime_config) -> None:
    updated = runtime_config.__class__(**{**runtime_config.__dict__, "ai_provider": "unknown"})
    with pytest.raises(Exception, match="Неизвестный AI provider"):
        build_ai_provider(updated)
