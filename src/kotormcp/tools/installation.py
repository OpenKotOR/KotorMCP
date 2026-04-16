"""Installation management tools: detect, load, info."""

from __future__ import annotations

from typing import Any

from mcp import types
from pykotor.common.misc import Game
from pykotor.tools.validation import get_installation_summary

from kotormcp.schemas.inputs import (
    GetInstallationGraphInput,
    GetInstallationSnapshotInput,
    LoadInstallationInput,
    OpenInstallationInput,
)
from kotormcp.state import (
    DEFAULT_PATH_CACHE,
    get_installation_snapshot,
    iter_candidate_paths,
    load_installation,
    open_installation_snapshot,
    resolve_game,
)
from kotormcp.utils.formatting import json_content


def get_tools() -> list[types.Tool]:
    """Return tool definitions for installation management (read-only, local filesystem)."""
    return [
        types.Tool(
            name="detectInstallations",
            description="Use when you need to discover candidate K1/K2 installation paths (env vars and platform defaults). Read-only.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="loadInstallation",
            description="Use when you need to activate an installation in memory for subsequent tools. Read-only; does not modify disk.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1, k2, or tsl"},
                    "path": {"type": "string", "description": "Optional absolute path override"},
                },
                "required": ["game"],
            },
        ),
        types.Tool(
            name="openInstallation",
            description="Build or reuse a compacted in-memory installation snapshot and return a handle for paged follow-up queries. Read-only; does not write to disk.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1, k2, or tsl"},
                    "path": {"type": "string", "description": "Optional absolute path override"},
                    "refresh": {"type": "boolean", "description": "Force snapshot rebuild instead of reusing a cached snapshot"},
                },
                "required": ["game"],
            },
        ),
        types.Tool(
            name="getInstallationSnapshot",
            description="Page through a compacted in-memory installation snapshot created by openInstallation. Use includeData=true for compacted per-resource documents.",
            inputSchema={
                "type": "object",
                "properties": {
                    "snapshotId": {"type": "string", "description": "Snapshot handle returned by openInstallation"},
                    "resourceTypes": {"type": "array", "items": {"type": "string"}, "description": "Optional resource type filter"},
                    "resrefQuery": {"type": "string", "description": "Case-insensitive substring filter for resource name or resref"},
                    "sourceQuery": {"type": "string", "description": "Case-insensitive substring filter for source/container paths"},
                    "includeData": {"type": "boolean", "description": "Include compacted per-resource documents instead of metadata-only summaries"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Max results per page"},
                    "offset": {"type": "integer", "minimum": 0, "description": "Skip first N results"},
                },
                "required": ["snapshotId"],
            },
        ),
        types.Tool(
            name="getInstallationGraph",
            description="Page through canonical dependency edges extracted from an in-memory installation snapshot created by openInstallation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "snapshotId": {"type": "string", "description": "Snapshot handle returned by openInstallation"},
                    "edgeKinds": {"type": "array", "items": {"type": "string"}, "description": "Optional edge kind filter"},
                    "targetTypes": {"type": "array", "items": {"type": "string"}, "description": "Optional target resource type filter"},
                    "query": {"type": "string", "description": "Case-insensitive filter for target name, source resource, or field path"},
                    "sourceQuery": {"type": "string", "description": "Case-insensitive filter for source document path or source resource path"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Max results per page"},
                    "offset": {"type": "integer", "minimum": 0, "description": "Skip first N results"}
                },
                "required": ["snapshotId"],
            },
        ),
        types.Tool(
            name="kotor_installation_info",
            description="Use when you need installation summary: path, game, valid, errors, missing files, module/override counts. Loads installation if not cached.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1, k2, or tsl"},
                    "path": {"type": "string", "description": "Optional absolute path override"},
                },
                "required": ["game"],
            },
        ),
    ]


async def handle_detect_installations(_arguments: dict[str, Any]) -> types.CallToolResult:
    """Enumerate candidate paths for K1 and K2."""
    payload = {}
    for game in (Game.K1, Game.K2):
        default_keys = {str(path).lower() for path in DEFAULT_PATH_CACHE.get(game, [])}
        details = []
        for candidate in iter_candidate_paths(game, None):
            key = str(candidate).lower()
            details.append(
                {
                    "path": str(candidate),
                    "exists": candidate.is_dir(),
                    "label": "default" if key in default_keys else "env",
                },
            )
        payload[game.name] = details
    return json_content(payload)


async def handle_load_installation(arguments: dict[str, Any]) -> types.CallToolResult:
    """Load and cache an installation for the given game."""
    inp = LoadInstallationInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game as k1 or k2."
        raise ValueError(msg)
    installation = load_installation(game, inp.path)
    return json_content({"game": game.name, "path": str(installation.path())})


async def handle_open_installation(arguments: dict[str, Any]) -> types.CallToolResult:
    """Build or reuse a compacted in-memory snapshot for the given installation."""
    inp = OpenInstallationInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game as k1 or k2."
        raise ValueError(msg)
    snapshot, created = open_installation_snapshot(game, inp.path, refresh=inp.refresh)
    return json_content(snapshot.open_payload(cached=not created))


async def handle_get_installation_snapshot(arguments: dict[str, Any]) -> types.CallToolResult:
    """Page through a compacted in-memory installation snapshot."""
    inp = GetInstallationSnapshotInput.model_validate(arguments)
    snapshot = get_installation_snapshot(inp.snapshotId)
    return json_content(
        snapshot.page(
            limit=inp.limit,
            offset=inp.offset,
            include_data=inp.includeData,
            resource_types=inp.resourceTypes,
            resref_query=inp.resrefQuery,
            source_query=inp.sourceQuery,
        )
    )


async def handle_get_installation_graph(arguments: dict[str, Any]) -> types.CallToolResult:
    """Page through canonical dependency edges from a compacted installation snapshot."""
    inp = GetInstallationGraphInput.model_validate(arguments)
    snapshot = get_installation_snapshot(inp.snapshotId)
    return json_content(
        snapshot.page_graph(
            limit=inp.limit,
            offset=inp.offset,
            edge_kinds=inp.edgeKinds,
            target_types=inp.targetTypes,
            query=inp.query,
            source_query=inp.sourceQuery,
        )
    )


async def handle_installation_info(arguments: dict[str, Any]) -> types.CallToolResult:
    """Return installation summary (path, game, valid, errors, missing, counts)."""
    inp = LoadInstallationInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game as k1 or k2."
        raise ValueError(msg)
    installation = load_installation(game, inp.path)
    summary = get_installation_summary(installation)
    return json_content(summary)
