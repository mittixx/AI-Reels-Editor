from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from core.config import RuntimeConfig
from core.errors import AIUnavailableError, DependencyError
from models.artifacts import EditPlan, SpeechAnalysis, TimeRange, VisualItem, VisualPlan

T = TypeVar("T", bound=BaseModel)


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


class MockProvider(BaseAIProvider):
    name = "mock"

    def generate(
        self,
        purpose: str,
        prompt: str,
        context: dict[str, Any],
        output_model: type[T],
    ) -> T:
        raise AIUnavailableError(
            "MockProvider временно отключён"
        )


class OpenAIProvider(BaseAIProvider):
    name = "openai"

    def __init__(self, config: RuntimeConfig) -> None:
        if not config.openai_api_key:
            raise AIUnavailableError(
                "OPENAI_API_KEY не указан"
            )

        from openai import OpenAI

        self.client = OpenAI(
            api_key=config.openai_api_key,
            timeout=120.0,
            max_retries=2,
        )
        self.model = config.openai_model

    def generate(self, purpose: str, prompt: str, context: dict[str, Any], output_model: type[T]) -> T:
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
                    "content": json.dumps(context, ensure_ascii=False),
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
        raise AIUnavailableError(
            f"OpenAI request для {purpose} не выполнен: {type(exc).__name__}"
        ) from exc
    if config.ai_provider == "mock":
        return MockProvider()

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

    return path.read_text(encoding="utf-8")