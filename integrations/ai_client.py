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

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
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
                ],
                text_format=output_model,
            )

            parsed = response.output_parsed

            if parsed is None:
                raise AIUnavailableError(
                    "AI не вернул структурированный результат"
                )

            return output_model.model_validate(parsed)

        except AIUnavailableError:
            raise

        except Exception as exc:
            LOGGER.error(
                "OPENAI_DIAGNOSTIC %s",
                json.dumps(self._diagnostic_payload(purpose, exc), ensure_ascii=False, default=str),
            )

            raise AIUnavailableError(
                f"OpenAI request для {purpose} не выполнен: {type(exc).__name__}"
            ) from exc

    def _diagnostic_payload(self, purpose: str, exc: Exception) -> dict[str, Any]:
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
        return {
            "purpose": purpose,
            "api_key_configured": self.api_key_configured,
            "model": self.model,
            "endpoint": self.endpoint,
            "http_status": status,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
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
