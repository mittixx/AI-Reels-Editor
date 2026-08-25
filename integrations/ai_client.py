from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from core.config import RuntimeConfig
from core.errors import AIUnavailableError, DependencyError
from models.artifacts import EditPlan, SpeechAnalysis, VisualPlan

T = TypeVar("T", bound=BaseModel)
LOGGER = logging.getLogger(__name__)
EDIT_RANGE_TOLERANCE = 0.001


class BaseAIProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(
        self,
        purpose: str,
        prompt: str,
        context: dict[str, Any],
        output_model: type[T],
    ) -> T:
        ...


class OpenAIProvider(BaseAIProvider):
    name = "openai"

    def __init__(self, config: RuntimeConfig) -> None:
        from openai import OpenAI

        if not config.openai_api_key:
            raise AIUnavailableError(
                "OPENAI_API_KEY не указан"
            )

        self.client = OpenAI(
            api_key=config.openai_api_key,
            timeout=120.0,
            max_retries=2,
        )

        self.model = config.openai_model
        self.api_key_configured = bool(config.openai_api_key)
        self.endpoint = f"{str(self.client.base_url).rstrip('/')}/responses"


    def generate(
        self,
        purpose: str,
        prompt: str,
        context: dict[str, Any],
        output_model: type[T],
    ) -> T:
        input_payload = [
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    context,
                    ensure_ascii=False,
                ),
            },
        ]
        request_stage = "responses.parse"
        try:
            if output_model is EditPlan:
                request_stage = "responses.create.raw_json"
                response = self.client.responses.create(
                    model=self.model,
                    input=input_payload,
                    text={"format": self._raw_json_format(output_model)},
                )
                request_stage = "edit_plan.decode_raw_json"
                parsed = json.loads(self._response_text(response))
                request_stage = "edit_plan.normalize_ranges"
                parsed = self._normalize_edit_plan_ranges(parsed)
            else:
                response = self.client.responses.parse(
                    model=self.model,
                    input=input_payload,
                    text_format=output_model,
                )
                parsed = response.output_parsed

            if parsed is None:
                raise AIUnavailableError(
                    "AI не вернул структурированный результат"
                )

            request_stage = "output_model.model_validate"
            return output_model.model_validate(parsed)

        except AIUnavailableError:
            raise

        except Exception as exc:
            LOGGER.error(
                "OPENAI_DIAGNOSTIC %s",
                json.dumps(
                    self._diagnostic_payload(purpose, exc, output_model, request_stage),
                    ensure_ascii=False,
                    default=str,
                ),
            )

            raise AIUnavailableError(
                f"OpenAI request для {purpose} не выполнен: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _raw_json_format(output_model: type[BaseModel]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "name": output_model.__name__,
            "schema": output_model.model_json_schema(),
            "strict": False,
        }

    @staticmethod
    def _response_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "output_text":
                    text = getattr(content, "text", None)
                    if isinstance(text, str) and text.strip():
                        return text
        raise AIUnavailableError("AI не вернул JSON для EditPlan")

    @staticmethod
    def _normalize_edit_plan_ranges(payload: Any) -> Any:
        """Normalize raw EditPlan JSON before Pydantic timeline validation."""
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        if not isinstance(payload, dict):
            return payload

        normalized = dict(payload)
        keep_ranges = normalized.get("keep_ranges")
        removed_ranges = normalized.get("removed_ranges")
        if not isinstance(keep_ranges, list) or not isinstance(removed_ranges, list):
            return normalized

        keep_data = [OpenAIProvider._range_mapping(item) for item in keep_ranges]
        removed_data = [OpenAIProvider._range_mapping(item) for item in removed_ranges]
        if any(item is None for item in keep_data) or any(item is None for item in removed_data):
            return normalized

        valid_keep_data = [item for item in keep_data if item is not None]
        valid_removed_data = [
            item for item in removed_data
            if item is not None and not OpenAIProvider._is_empty_removed_range(item)
        ]
        keep_intervals = [OpenAIProvider._range_interval(item) for item in valid_keep_data]
        removed_intervals = [OpenAIProvider._range_interval(item) for item in valid_removed_data]
        if any(item is None for item in [*keep_intervals, *removed_intervals]):
            return normalized

        typed_keep_intervals = [item for item in keep_intervals if item is not None]
        typed_removed_intervals = [item for item in removed_intervals if item is not None]

        # Keep ranges are the primary timeline. A removed range that exactly
        # duplicates one is redundant, so discard it instead of deleting keep.
        filtered_removed = [
            (data, interval)
            for data, interval in zip(valid_removed_data, typed_removed_intervals, strict=True)
            if not any(OpenAIProvider._same_interval(interval, keep) for keep in typed_keep_intervals)
        ]

        normalized_keep: list[dict[str, Any]] = []
        for keep in valid_keep_data:
            interval = OpenAIProvider._range_interval(keep)
            if interval is None:
                return normalized
            fragments = [interval]
            for _, removed in filtered_removed:
                fragments = OpenAIProvider._subtract_interval(
                    fragments,
                    removed[0],
                    removed[1],
                )
                if not fragments:
                    break

            for index, (start, end) in enumerate(fragments, start=1):
                fragment = dict(keep)
                fragment["start"] = start
                fragment["end"] = end
                if len(fragments) > 1:
                    fragment["id"] = f"{keep.get('id', 'keep')}_{index}"
                normalized_keep.append(fragment)

        normalized["keep_ranges"] = normalized_keep
        normalized["removed_ranges"] = [data for data, _ in filtered_removed]
        normalized["estimated_duration"] = sum(
            item["end"] - item["start"] for item in normalized_keep
        )
        return normalized

    @staticmethod
    def _range_mapping(value: Any) -> dict[str, Any] | None:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        return dict(value) if isinstance(value, dict) else None

    @staticmethod
    def _range_interval(value: Any) -> tuple[float, float] | None:
        data = OpenAIProvider._range_mapping(value)
        if data is None:
            return None
        try:
            start = float(data["start"])
            end = float(data["end"])
        except (KeyError, TypeError, ValueError):
            return None
        return (start, end) if end > start else None

    @staticmethod
    def _is_empty_removed_range(value: dict[str, Any]) -> bool:
        try:
            return float(value["end"]) <= float(value["start"])
        except (KeyError, TypeError, ValueError):
            return False

    @staticmethod
    def _same_interval(
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> bool:
        return (
            abs(first[0] - second[0]) <= EDIT_RANGE_TOLERANCE
            and abs(first[1] - second[1]) <= EDIT_RANGE_TOLERANCE
        )

    @staticmethod
    def _subtract_interval(
        fragments: list[tuple[float, float]],
        removed_start: float,
        removed_end: float,
    ) -> list[tuple[float, float]]:
        result: list[tuple[float, float]] = []
        for start, end in fragments:
            # Snap merely adjacent boundaries. They are valid and must not be
            # mistaken for an overlap by later floating-point comparisons.
            if abs(end - removed_start) <= EDIT_RANGE_TOLERANCE:
                end = removed_start
            if abs(start - removed_end) <= EDIT_RANGE_TOLERANCE:
                start = removed_end

            if end <= removed_start + EDIT_RANGE_TOLERANCE or start >= removed_end - EDIT_RANGE_TOLERANCE:
                result.append((start, end))
                continue

            # A real removed range is cut from keep. Touching boundaries are
            # preserved, while a range crossing the cut is split in two.
            if start < removed_start - EDIT_RANGE_TOLERANCE:
                result.append((start, removed_start))
            if end > removed_end + EDIT_RANGE_TOLERANCE:
                result.append((removed_end, end))
        return result

    def _diagnostic_payload(
        self,
        purpose: str,
        exc: Exception,
        output_model: type[BaseModel] | None = None,
        request_stage: str | None = None,
    ) -> dict[str, Any]:
        response = getattr(exc, "response", None)
        status = getattr(exc, "status_code", None)
        if status is None and response is not None:
            status = getattr(response, "status_code", None)
        body = getattr(exc, "body", None)
        if body is None and response is not None:
            try:
                body = response.text
            except Exception:  # pragma: no cover - defensive SDK compatibility
                body = None
        validation_errors = None
        errors = getattr(exc, "errors", None)
        if callable(errors):
            try:
                validation_errors = errors()
            except Exception:  # pragma: no cover - defensive SDK compatibility
                validation_errors = None
        response_format = None
        if output_model is not None:
            uses_raw_edit_json = purpose == "edit_plan"
            response_format = {
                "sdk_method": "responses.create" if uses_raw_edit_json else "responses.parse",
                "sdk_argument": "text.format" if uses_raw_edit_json else "text_format",
                "pydantic_model": output_model.__name__,
                "json_schema": output_model.model_json_schema(),
            }
        return {
            "purpose": purpose,
            "api_key_configured": self.api_key_configured,
            "model": self.model,
            "endpoint": self.endpoint,
            "request_stage": request_stage,
            "response_format": response_format,
            "http_status": status,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "error_repr": repr(exc),
            "validation_errors": validation_errors,
            "error_body": body,
        }



def build_ai_provider(config: RuntimeConfig) -> BaseAIProvider:

    if config.ai_provider == "openai":
        return OpenAIProvider(config)

    raise DependencyError(
        f"Неизвестный AI provider: {config.ai_provider}"
    )



def read_prompt(root: Path, name: str) -> str:

    path = root / "prompts" / name

    if not path.is_file():
        raise DependencyError(
            f"Prompt не найден: {path}"
        )

    return path.read_text(
        encoding="utf-8"
    )
