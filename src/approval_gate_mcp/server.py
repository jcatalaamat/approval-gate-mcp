"""MCP server (stdio). Three tools in front of every operation; the tenant comes from the environment."""

import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .dispatch import Dispatcher
from .errors import GateError
from .tenant import Tenant


def build_server(dispatcher: Dispatcher) -> Server:
    app = Server("approval-gate")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="discover",
                description="Browse available operations by category (notes, spend).",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_schema",
                description="Get the input schema for one operation, e.g. 'notes.read'.",
                inputSchema={"type": "object", "properties": {"operation": {"type": "string"}}, "required": ["operation"]},
            ),
            Tool(
                name="execute",
                description=(
                    "Run an operation. Operations marked requires_confirmation return a preview and a confirm_token "
                    "and do nothing until execute is called again with that token. Never confirm until the user has "
                    "approved the exact params shown in the preview."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"operation": {"type": "string"}, "params": {"type": "object"}},
                    "required": ["operation"],
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "discover":
                text = json.dumps(dispatcher.discover(), indent=2)
            elif name == "get_schema":
                op = dispatcher.get_schema(arguments["operation"])
                text = json.dumps(op, indent=2) if op else f"Unknown operation: {arguments['operation']}"
            elif name == "execute":
                text = dispatcher.execute(arguments["operation"], arguments.get("params") or {})
            else:
                raise GateError(f"unknown tool '{name}'")
        except GateError as e:
            text = f"Error: {e}"
        return [TextContent(type="text", text=text)]

    return app


async def main() -> None:
    app = build_server(Dispatcher(Tenant.from_env()))
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
