"""Walkmesh (BWM) tools: validation diagram for LLM context."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from mcp import types
from pykotor.extract.installation import SearchLocation
from pykotor.resource.formats.bwm import read_bwm
from pykotor.resource.type import ResourceType
from pykotor.tools.walkmesh_render_diagram import render_bwm_validation_diagram_lines

from kotormcp.state import load_installation, resolve_game


def get_tools() -> list[types.Tool]:
    """Tool definitions for walkmesh validation diagram (quality context for agents)."""
    return [
        types.Tool(
            name="kotor_walkmesh_validation_diagram",
            description="Get a text validation diagram for a walkmesh (BWM/WOK): perimeter, transitions, outer boundary. Use when you need to understand an area's walkable layout, door links, or boundary for modding or debugging. Read-only; returns plain text (no ANSI).",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "resref": {"type": "string", "description": "Walkmesh resref (e.g. 203tell for 203tell.wok)"},
                    "use_color": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, include ANSI color codes (e.g. for terminal); default false for plain text in MCP.",
                    },
                },
                "required": ["game", "resref"],
            },
        ),
    ]


async def handle_walkmesh_validation_diagram(arguments: dict[str, Any]) -> types.CallToolResult:
    """Load BWM from installation and return validation diagram lines as plain text."""
    game_str = arguments.get("game")
    resref = arguments.get("resref")
    if not game_str or not resref:
        raise ValueError("game and resref are required")
    game = resolve_game(game_str)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    order = [SearchLocation.OVERRIDE, SearchLocation.CUSTOM_FOLDERS, SearchLocation.MODULES, SearchLocation.CHITIN]
    # Resref may or may not include .wok
    resref_clean = resref.strip().lower().removesuffix(".wok")
    result = installation.resource(resref_clean, ResourceType.WOK, order=order)
    if result is None:
        raise ValueError(f"Walkmesh {resref_clean}.wok not found.")
    bwm = read_bwm(BytesIO(result.data))
    use_color = arguments.get("use_color", False)
    lines = render_bwm_validation_diagram_lines(bwm, use_color=use_color)
    return types.CallToolResult(content=[types.TextContent(type="text", text="\n".join(lines))])
