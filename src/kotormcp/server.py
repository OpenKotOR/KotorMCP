"""KotorMCP - Model Context Protocol server for Knights of the Old Republic resources.

This server exposes context-rich tools tailored for AI agents. It focuses on installation
management, resource discovery, and journal/plot inspection workflows that mirror the
pipelines used in `Tools/Pykotorcli` and helper scripts under `scripts/`.

Implementation notes:
    * Resource scanning logic mirrors `scripts/investigate_module_structure.py:35-120`.
    * Journal summarisation follows the same structure documented in
      `vendor/xoreos/src/engines/nwn2/journal.cpp:35-78`, ensuring parity with established
      engine reimplementations.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

try:
    from uvicorn import Config
    from uvicorn import Server as UvicornServer
except ImportError:
    UvicornServer = None  # type: ignore[assignment, misc]
    Config = None  # type: ignore[assignment, misc]

import mcp.server.sse
import mcp.server.stdio
import mcp.server.streamable_http
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from kotormcp import mcp_resources
from kotormcp.tools import get_all_tools, handle_tool


SERVER = Server("KotorMCP")


@SERVER.list_tools()
async def list_tools() -> list:
    return get_all_tools()


@SERVER.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]):
    return await handle_tool(name, arguments)


# MCP resources (kotor:// URI scheme) for passive context injection
@SERVER.list_resources()
async def list_resources():
    return await mcp_resources.list_resources()


@SERVER.read_resource()
async def read_resource(uri: str):
    return await mcp_resources.read_resource(uri)


async def _run_stdio() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await SERVER.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="KotorMCP",
                server_version="0.1.0",
                capabilities=SERVER.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
                notification_options=NotificationOptions(),
            ),
        )


async def _run_sse(port: int = 8000, host: str = "localhost") -> None:
    """Run the server with SSE (Server-Sent Events) transport.

    The SSE transport uses Server-Sent Events for one-way streaming from server to client,
    and HTTP POST for client-to-server messages.
    """
    if UvicornServer is None or Config is None:
        msg = "uvicorn is required for SSE mode. Install with: pip install uvicorn[standard]"
        raise ImportError(msg)

    transport = mcp.server.sse.SseServerTransport(endpoint="/mcp")

    async def asgi_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "")

            if method == "GET" and path == "/mcp":
                await transport.connect_sse(scope, receive, send)
            elif method == "POST" and path == "/mcp":
                await transport.handle_post_message(scope, receive, send)
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [[b"content-type", b"text/plain"]],
                    },
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Not Found",
                    },
                )
        else:
            msg = f"Unsupported scope type: {scope['type']}"
            raise ValueError(msg)

    config = Config(
        app=asgi_app,
        host=host,
        port=port,
        log_level="info",
    )

    server = UvicornServer(config)
    await server.serve()


async def _run_http(port: int = 8000, host: str = "localhost") -> None:
    """Run the server with HTTP streaming transport."""
    if UvicornServer is None or Config is None:
        msg = "uvicorn is required for HTTP mode. Install with: pip install uvicorn[standard]"
        raise ImportError(msg)

    transport = mcp.server.streamable_http.StreamableHTTPServerTransport(mcp_session_id=None)

    async def asgi_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            method = scope.get("method", "")

            if method in ("GET", "POST"):
                await transport.handle_request(scope, receive, send)
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 405,
                        "headers": [[b"content-type", b"text/plain"]],
                    },
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Method Not Allowed",
                    },
                )
        else:
            msg = f"Unsupported scope type: {scope['type']}"
            raise ValueError(msg)

    config = Config(
        app=asgi_app,
        host=host,
        port=port,
        log_level="info",
    )

    server = UvicornServer(config)
    await server.serve()


def _get_invocation_command() -> str:
    """Get the actual command used to invoke the CLI."""
    if not sys.argv:
        return "kotormcp"

    is_uv_run = False
    try:
        import psutil  # type: ignore[import-untyped]  # noqa: PLC0415

        current_process = psutil.Process()
        parent = current_process.parent()
        if parent and "uv" in parent.name().lower():
            is_uv_run = True
    except (ImportError, Exception):
        if any("UV" in k.upper() for k in os.environ):
            is_uv_run = True

    script_path = Path(sys.argv[0]).resolve()
    cwd = Path.cwd().resolve()

    try:
        rel_script = script_path.relative_to(cwd)
        rel_script_str = str(rel_script).replace("\\", "/")
    except ValueError:
        rel_script_str = str(script_path)

    if is_uv_run:
        return f"uv run {rel_script_str}"

    if len(sys.argv) >= 3 and sys.argv[1] == "-m":
        return f"python -m {sys.argv[2]}"

    python_exe = Path(sys.executable).name.lower()
    if python_exe in ("python", "python3", "python.exe", "python3.exe", "py", "py.exe"):
        return f"python {rel_script_str}"

    return rel_script_str


def main(argv: list[str] | None = None) -> None:
    prog = _get_invocation_command()
    parser = argparse.ArgumentParser(prog=prog, description="Run the KotorMCP server.")
    parser.add_argument(
        "--mode",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport to use (stdio for command-line, sse for Server-Sent Events, http for HTTP streaming)",
    )
    parser.add_argument("--host", default="localhost", help="Host to bind to for HTTP/SSE modes (default: localhost)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to for HTTP/SSE modes (default: 8000)")
    args = parser.parse_args(argv)

    if args.mode == "stdio":
        asyncio.run(_run_stdio())
    elif args.mode == "sse":
        asyncio.run(_run_sse(port=args.port, host=args.host))
    elif args.mode == "http":
        asyncio.run(_run_http(port=args.port, host=args.host))
    else:
        msg = f"Unsupported mode: {args.mode}"
        raise SystemExit(msg)


if __name__ == "__main__":
    main()
