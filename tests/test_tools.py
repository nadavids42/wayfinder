import json

import pytest

from wayfinder.llm import ToolCall
from wayfinder.tools import Tool, ToolRegistry


def sample_search(query: str) -> list[dict]:
    """Harmless demonstration search function."""

    return [
        {
            "title": "Applied AI Engineer",
            "query": query,
        }
    ]


@pytest.fixture
def registry():
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="search_jobs",
            description="Search for job opportunities",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            function=sample_search,
        )
    )

    return registry


def make_call(
    name: str = "search_jobs",
    arguments: str = '{"query": "AI Engineer"}',
) -> ToolCall:

    return ToolCall(
        id="call_123",
        name=name,
        arguments=arguments,
    )


def test_register_tool(registry):
    schemas = registry.schemas()

    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "search_jobs"


def test_execute_tool(registry):
    result = registry.execute(make_call())

    assert result.success is True
    assert result.result[0]["title"] == "Applied AI Engineer"
    assert result.result[0]["query"] == "AI Engineer"
    assert result.tool_call_id == "call_123"


def test_unknown_tool(registry):
    result = registry.execute(
        make_call(name="delete_database")
    )

    assert result.success is False
    assert "Unknown tool" in result.error


def test_invalid_json(registry):
    result = registry.execute(
        make_call(arguments="{invalid json}")
    )

    assert result.success is False
    assert result.error == "Invalid JSON arguments"


def test_missing_required_argument(registry):
    result = registry.execute(
        make_call(arguments="{}")
    )

    assert result.success is False
    assert "Missing required argument" in result.error


def test_invalid_argument_type(registry):
    result = registry.execute(
        make_call(arguments='{"query": 123}')
    )

    assert result.success is False
    assert "Invalid type" in result.error


def test_unexpected_argument(registry):
    result = registry.execute(
        make_call(
            arguments='{"query": "AI", "command": "rm -rf /"}'
        )
    )

    assert result.success is False
    assert "Unexpected argument" in result.error


def test_duplicate_registration(registry):
    with pytest.raises(ValueError):
        registry.register(
            Tool(
                name="search_jobs",
                description="Duplicate",
                parameters={},
                function=sample_search,
            )
        )


def test_tool_execution_failure(registry):
    def failing_tool(query: str):
        raise RuntimeError("Simulated failure")

    registry.register(
        Tool(
            name="failing_tool",
            description="A tool that fails",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            function=failing_tool,
        )
    )

    result = registry.execute(
        make_call(name="failing_tool")
    )

    assert result.success is False
    assert "Simulated failure" in result.error


def test_result_serialization(registry):
    result = registry.execute(make_call())

    serialized = json.loads(result.to_json())

    assert serialized["success"] is True
    assert serialized["tool_call_id"] == "call_123"