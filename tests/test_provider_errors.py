from __future__ import annotations

from types import SimpleNamespace

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


def test_edit_plan_generate_normalizes_raw_json_before_validation() -> None:
    payload = {
        "project_id": "project",
        "keep_ranges": [
            {"id": "keep", "start": 26.3, "end": 34.3},
        ],
        "removed_ranges": [
            {"id": "removed", "start": 28.54, "end": 28.66, "action": "cut"},
        ],
        "estimated_duration": 8.0,
    }

    class FakeResponses:
        @staticmethod
        def create(**kwargs: object) -> SimpleNamespace:
            assert kwargs["text"] == {"format": OpenAIProvider._raw_json_format(EditPlan)}
            return SimpleNamespace(output_text=json.dumps(payload))

    provider = object.__new__(OpenAIProvider)
    provider.client = SimpleNamespace(responses=FakeResponses())
    provider.model = "test-model"

    plan = provider.generate("edit_plan", "prompt", {}, EditPlan)

    assert [(item.start, item.end) for item in plan.keep_ranges] == [
        (26.3, 28.54),
        (28.66, 34.3),
    ]
    assert [(item.start, item.end) for item in plan.removed_ranges] == [(28.54, 28.66)]
    assert plan.estimated_duration == pytest.approx(7.88)


def test_edit_plan_normalizer_keeps_adjacent_ranges_and_drops_matching_removed() -> None:
    payload = {
        "project_id": "project",
        "keep_ranges": [
            {"id": "keep", "start": 40.06, "end": 42.28},
        ],
        "removed_ranges": [
            {"id": "overlap", "start": 42.0, "end": 42.46, "action": "cut"},
            {"id": "duplicate", "start": 40.06, "end": 42.28, "action": "cut"},
        ],
        "estimated_duration": 2.22,
    }

    plan = EditPlan.model_validate(OpenAIProvider._normalize_edit_plan_ranges(payload))

    assert [(item.id, item.start, item.end) for item in plan.keep_ranges] == [
        ("keep", 40.06, 42.0),
    ]
    assert [(item.id, item.start, item.end) for item in plan.removed_ranges] == [
        ("overlap", 42.0, 42.46),
    ]
    assert plan.estimated_duration == pytest.approx(1.94)
