import httpx
import pytest

from wayfinder.llm import (
    Message,
    ModelClient,
    ModelConfig,
    ModelError,
)


@pytest.fixture
def config():
    return ModelConfig(
        model="test-model",
        base_url="http://localhost:9999/v1",
    )


def test_model_response(monkeypatch, config):

    def mock_post(self, url, **kwargs):
        request = httpx.Request("POST", url)

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hello from Wayfinder",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            },
            request=request,
        )

    monkeypatch.setattr(
        httpx.Client,
        "post",
        mock_post,
    )

    client = ModelClient(config)

    result = client.complete([
        Message(
            role="user",
            content="Hello",
        )
    ])

    assert result.content == "Hello from Wayfinder"
    assert result.finish_reason == "stop"
    assert result.usage["completion_tokens"] == 5


def test_tool_call_response(monkeypatch, config):

    def mock_post(self, url, **kwargs):
        request = httpx.Request("POST", url)

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_123",
                                    "type": "function",
                                    "function": {
                                        "name": "search_jobs",
                                        "arguments": '{"query":"AI engineer"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            request=request,
        )

    monkeypatch.setattr(
        httpx.Client,
        "post",
        mock_post,
    )

    client = ModelClient(config)

    result = client.complete([
        Message(
            role="user",
            content="Find AI engineering jobs",
        )
    ])

    assert result.content is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search_jobs"
    assert result.tool_calls[0].id == "call_123"


def test_http_error(monkeypatch, config):

    def mock_post(self, url, **kwargs):
        request = httpx.Request("POST", url)

        return httpx.Response(
            500,
            request=request,
        )

    monkeypatch.setattr(
        httpx.Client,
        "post",
        mock_post,
    )

    client = ModelClient(config)

    with pytest.raises(ModelError):
        client.complete([
            Message(
                role="user",
                content="Hello",
            )
        ])


def test_invalid_response(monkeypatch, config):

    def mock_post(self, url, **kwargs):
        request = httpx.Request("POST", url)

        return httpx.Response(
            200,
            json={"unexpected": "structure"},
            request=request,
        )

    monkeypatch.setattr(
        httpx.Client,
        "post",
        mock_post,
    )

    client = ModelClient(config)

    with pytest.raises(ModelError):
        client.complete([
            Message(
                role="user",
                content="Hello",
            )
        ])