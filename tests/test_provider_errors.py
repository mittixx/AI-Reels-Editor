from __future__ import annotations

import pytest

from integrations.ai_client import OpenAIProvider, build_ai_provider
from models.artifacts import EditPlan


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

    payload = provider._diagnostic_payload(
        "speech_analysis", PermissionDeniedError("Project access denied"), EditPlan, "responses.parse",
    )

    assert payload["purpose"] == "speech_analysis"
    assert payload["api_key_configured"] is True
    assert payload["model"] == "gpt-5.6-luna"
    assert payload["endpoint"] == "https://api.openai.com/v1/responses"
    assert payload["request_stage"] == "responses.parse"
    assert payload["response_format"]["sdk_argument"] == "text_format"
    assert payload["response_format"]["pydantic_model"] == "EditPlan"
    assert payload["response_format"]["json_schema"] == EditPlan.model_json_schema()
    assert payload["http_status"] == 403
    assert payload["error_type"] == "PermissionDeniedError"
    assert payload["error_message"] == "Project access denied"
    assert payload["validation_errors"] is None
    assert payload["error_body"] == {"error": {"message": "Project access denied", "code": "project_access_denied"}}


def test_openai_diagnostic_records_full_validation_errors() -> None:
    provider = object.__new__(OpenAIProvider)
    provider.api_key_configured = True
    provider.model = "gpt-5.6-luna"
    provider.endpoint = "https://api.openai.com/v1/responses"
    with pytest.raises(Exception) as captured:
        EditPlan.model_validate({"project_id": "p", "keep_ranges": [], "estimated_duration": 0})

    payload = provider._diagnostic_payload("edit_plan", captured.value, EditPlan, "output_model.model_validate")

    assert payload["purpose"] == "edit_plan"
    assert payload["request_stage"] == "output_model.model_validate"
    assert payload["error_type"] == "ValidationError"
    assert payload["validation_errors"]
    assert "keep_ranges" in payload["error_message"]
