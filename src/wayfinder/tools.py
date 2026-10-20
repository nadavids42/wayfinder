"""Tool registration, validation, and execution for Wayfinder."""

import json
from dataclasses import dataclass
from typing import Any, Callable

from wayfinder.llm import ToolCall


@dataclass
class Tool:
    """A Python function exposed to the language model."""

    name: str
    description: str
    parameters: dict[str, Any]
    function: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        """Return the OpenAI-compatible tool definition."""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    """Structured result of a tool execution."""

    tool_call_id: str
    name: str
    success: bool
    result: Any = None
    error: str | None = None

    def to_json(self) -> str:
        """Serialize the result for consumption by an LLM."""

        return json.dumps({
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "success": self.success,
            "result": self.result,
            "error": self.error,
        })


class ToolRegistry:
    """Registry of tools available to the Wayfinder agent."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool by name."""

        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        """Return tool definitions for the model."""

        return [
            tool.schema()
            for tool in self._tools.values()
        ]

    def execute(self, call: ToolCall) -> ToolResult:
        """Validate and execute a model-requested tool."""

        tool = self._tools.get(call.name)

        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                success=False,
                error=f"Unknown tool: {call.name}",
            )

        try:
            arguments = json.loads(call.arguments)

        except json.JSONDecodeError:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                success=False,
                error="Invalid JSON arguments",
            )

        if not isinstance(arguments, dict):
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                success=False,
                error="Tool arguments must be a JSON object",
            )

        validation_error = self._validate(
            tool.parameters,
            arguments,
        )

        if validation_error:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                success=False,
                error=validation_error,
            )

        try:
            result = tool.function(**arguments)

            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                success=True,
                result=result,
            )

        except Exception as exc:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                success=False,
                error=f"Tool execution failed: {exc}",
            )

    @staticmethod
    def _validate(
        schema: dict[str, Any],
        arguments: dict[str, Any],
    ) -> str | None:
        """Validate a limited subset of JSON Schema."""

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for name in required:
            if name not in arguments:
                return f"Missing required argument: {name}"

        for name, value in arguments.items():

            if name not in properties:
                return f"Unexpected argument: {name}"

            expected_type = properties[name].get("type")

            type_map = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "array": list,
                "object": dict,
            }

            python_type = type_map.get(expected_type)

            if python_type is None:
                return f"Unsupported argument type: {expected_type}"

            # Python bool is a subclass of int, so reject it
            # explicitly for numeric JSON Schema types.
            if expected_type in ("integer", "number"):
                valid = (
                    isinstance(value, python_type)
                    and not isinstance(value, bool)
                )
            else:
                valid = isinstance(value, python_type)

            if not valid:
                return (
                    f"Invalid type for '{name}': "
                    f"expected {expected_type}"
                )

        return None