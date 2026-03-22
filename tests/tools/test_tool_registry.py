"""Unit tests for ToolRegistry."""
from __future__ import annotations

from typing import Any

import pytest

from src.tools.base import BaseTool, ToolError
from src.tools.context import ToolContext
from src.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _EchoTool(BaseTool):
    name = "echo"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Echoes input.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> Any:
        return input


class _FailTool(BaseTool):
    name = "fail"

    @property
    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Always raises ToolError.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }

    def run(self, input: dict[str, Any], context: ToolContext) -> Any:
        raise ToolError("intentional failure", tool_name=self.name)


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


def test_register_and_get():
    reg = ToolRegistry()
    tool = _EchoTool()
    reg.register(tool)
    assert reg.get("echo") is tool


def test_register_duplicate_raises():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_EchoTool())


def test_get_unknown_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError, match="No tool named"):
        reg.get("does_not_exist")


def test_register_returns_self_for_chaining():
    reg = ToolRegistry()
    result = reg.register(_EchoTool())
    assert result is reg


def test_names_returns_all_registered():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    reg.register(_FailTool())
    assert set(reg.names()) == {"echo", "fail"}


def test_len():
    reg = ToolRegistry()
    assert len(reg) == 0
    reg.register(_EchoTool())
    assert len(reg) == 1


def test_contains():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    assert "echo" in reg
    assert "missing" not in reg


def test_schemas_returns_anthropic_schemas():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    schemas = reg.schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "echo"
    assert "input_schema" in schemas[0]


def test_dispatch_calls_run():
    reg = ToolRegistry()
    reg.register(_EchoTool())
    ctx = ToolContext()
    result = reg.dispatch("echo", {"key": "val"}, ctx)
    assert result == {"key": "val"}


def test_dispatch_propagates_tool_error():
    reg = ToolRegistry()
    reg.register(_FailTool())
    ctx = ToolContext()
    with pytest.raises(ToolError, match="intentional failure"):
        reg.dispatch("fail", {}, ctx)


def test_dispatch_unknown_tool_raises():
    reg = ToolRegistry()
    ctx = ToolContext()
    with pytest.raises(KeyError):
        reg.dispatch("ghost", {}, ctx)


# ---------------------------------------------------------------------------
# ToolError attributes
# ---------------------------------------------------------------------------


def test_tool_error_stores_tool_name():
    err = ToolError("oops", tool_name="my_tool")
    assert err.tool_name == "my_tool"
    assert str(err) == "oops"


def test_tool_error_default_tool_name():
    err = ToolError("plain error")
    assert err.tool_name == ""
