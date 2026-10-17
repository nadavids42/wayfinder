"""Provider-independent interface for OpenAI-compatible LLM APIs."""

import os
from dataclasses import dataclass, field
from typing import Any

import httpx


class ModelError(Exception):
    """Raised when model communication fails."""


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ModelResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    model: str
    base_url: str
    api_key: str | None = None
    timeout: float = 60.0
    max_tokens: int = 2048


class ModelClient:
    """Client for OpenAI-compatible chat completion endpoints."""

    def __init__(self, config: ModelConfig):
        self.config = config

    def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse:

        url = (
            self.config.base_url.rstrip("/")
            + "/chat/completions"
        )

        headers = {
            "Content-Type": "application/json",
        }

        if self.config.api_key:
            headers["Authorization"] = (
                f"Bearer {self.config.api_key}"
            )

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "max_tokens": self.config.max_tokens,
        }      

        if tools is not None:
            payload["tools"] = tools

        try:
            with httpx.Client(
                timeout=self.config.timeout
            ) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()
                data = response.json()

        except httpx.HTTPError as exc:
            raise ModelError(
                f"Model request failed: {exc}"
            ) from exc

        except ValueError as exc:
            raise ModelError(
                "Model returned invalid JSON"
            ) from exc

        try:
            choice = data["choices"][0]
            message = choice["message"]

            tool_calls = [
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=call["function"]["arguments"],
                )
                for call in message.get("tool_calls", [])
            ]

            return ModelResponse(
                content=message.get("content"),
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason"),
                usage=data.get("usage", {}),
            )

        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError(
                "Model returned an unexpected response structure"
            ) from exc


def load_model_config() -> ModelConfig:
    """Load model configuration from environment variables."""

    return ModelConfig(
        model=os.getenv("WAYFINDER_MODEL", "llama3.2"),
        base_url=os.getenv(
            "WAYFINDER_MODEL_BASE_URL",
            "http://localhost:11434/v1",
        ),
        api_key=os.getenv("WAYFINDER_MODEL_API_KEY"),
        max_tokens=int(
            os.getenv("WAYFINDER_MODEL_MAX_TOKENS", "2048")
        ),
    )