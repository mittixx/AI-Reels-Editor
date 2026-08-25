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


def test_openai_diagnostic_keeps_key_secret_and_reports_api_error() -> None:
    class PermissionDeniedError(Exception):
        status_code = 403
        body = {"error": {"message": "Project access denied", "code": "project_access_denied"}}

    provider = object.__new__(OpenAIProvider)
    provider.api_key_configured = True
    provider.model = "gpt-5.6-luna"
    provider.endpoint = "https://api.openai.com/v1/responses"

    payload = provider._diagnostic_payload("speech_analysis", PermissionDeniedError("Project access denied"))

    assert payload == {
        "purpose": "speech_analysis",
        "api_key_configured": True,
        "model": "gpt-5.6-luna",
        "endpoint": "https://api.openai.com/v1/responses",
        "http_status": 403,
        "error_type": "PermissionDeniedError",
        "error_message": "Project access denied",
        "error_body": {"error": {"message": "Project access denied", "code": "project_access_denied"}},
    }
