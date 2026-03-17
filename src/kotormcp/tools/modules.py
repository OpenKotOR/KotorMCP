"""Module operations: list_modules, describe_module, module_resources."""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from typing import Any

from mcp import types

from pykotor.extract.installation import SearchLocation
from pykotor.resource.formats.gff.gff_auto import read_gff
from pykotor.resource.type import ResourceType

from kotormcp.schemas.inputs import DescribeModuleInput, ListModulesInput, ModuleResourcesInput
from kotormcp.state import load_installation, resolve_game
from kotormcp.utils.formatting import json_content


def get_tools() -> list[types.Tool]:
    """Return tool definitions for module operations (read-only)."""
    return [
        types.Tool(
            name="kotor_list_modules",
            description="Use when you need all modules with human-readable area names (from ARE + TalkTable). Read-only.",
            inputSchema={
                "type": "object",
                "properties": {"game": {"type": "string", "description": "Game alias: k1 or k2"}},
                "required": ["game"],
            },
        ),
        types.Tool(
            name="kotor_describe_module",
            description="Use when you need full module analysis: ARE, LYT rooms, WOK list, resource counts, scripts. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "module_root": {"type": "string", "description": "Module root name (e.g. 003ebo, danm13)"},
                },
                "required": ["game", "module_root"],
            },
        ),
        types.Tool(
            name="kotor_module_resources",
            description="Use when you need a paginated list of all resources in a module (.rim + _s.rim + _dlg.erf). Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "module_root": {"type": "string", "description": "Module root name"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50, "description": "Max results per page"},
                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Skip first N results"},
                },
                "required": ["game", "module_root"],
            },
        ),
    ]


def _module_root_to_filenames(installation: Any, module_root: str) -> list[str]:
    """Return list of capsule filenames that belong to this module root."""
    root_lower = module_root.strip().lower()
    out: list[str] = []
    for filename in installation.modules_list():
        if installation.get_module_root(filename).lower() == root_lower:
            out.append(filename)
    return out


async def handle_list_modules(arguments: dict[str, Any]) -> types.CallToolResult:
    """List all modules with area names."""
    inp = ListModulesInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    names = installation.module_names()
    # Group by module root: root -> { area_name, files }
    root_to_info: dict[str, dict[str, Any]] = {}
    for filename, area_name in names.items():
        root = installation.get_module_root(filename)
        if root not in root_to_info:
            root_to_info[root] = {"module_root": root, "area_name": area_name or root, "files": []}
        root_to_info[root]["files"].append(filename)
    modules_list = list(root_to_info.values())
    return json_content({"count": len(modules_list), "modules": modules_list})


async def handle_describe_module(arguments: dict[str, Any]) -> types.CallToolResult:
    """Full module analysis: ARE, LYT, WOK list, resource counts, scripts."""
    inp = DescribeModuleInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    root = inp.module_root.strip()
    order = [SearchLocation.MODULES]
    are_res = installation.resource(root, ResourceType.ARE, order=order, module_root=root)
    lyt_res = installation.resource(root, ResourceType.LYT, order=order, module_root=root)
    wok_res = installation.resource(root, ResourceType.WOK, order=order, module_root=root)
    summary: dict[str, Any] = {
        "module_root": root,
        "area_name": installation.module_name(next(iter(_module_root_to_filenames(installation, root)), root + ".rim")) or root,
        "are": None,
        "lyt": None,
        "wok_list": [],
        "resource_counts": {},
        "script_list": [],
    }
    if are_res:
        try:
            gff = read_gff(BytesIO(are_res.data))
            summary["are"] = {"struct_id": gff.root.struct_id, "field_count": len(gff.root)}
        except Exception:
            summary["are"] = {"error": "Failed to parse ARE"}
    if lyt_res:
        try:
            gff = read_gff(BytesIO(lyt_res.data))
            room_list = gff.root.get_list("Room_List", default=[])
            summary["lyt"] = {"room_count": len(room_list)}
        except Exception:
            summary["lyt"] = {"error": "Failed to parse LYT"}
    if wok_res:
        summary["wok_list"] = [f"{root}.wok"]
    # Resource counts and script list from module resources
    files = _module_root_to_filenames(installation, root)
    type_counts: dict[str, int] = defaultdict(int)
    scripts: list[str] = []
    for f in files:
        for res in installation.module_resources(f):
            type_name = res.restype().name
            type_counts[type_name] = type_counts[type_name] + 1
            if type_name == "NCS":
                scripts.append(res.resname())
    summary["resource_counts"] = dict(type_counts)
    summary["script_list"] = sorted(set(scripts))[:100]
    return json_content(summary)


async def handle_module_resources(arguments: dict[str, Any]) -> types.CallToolResult:
    """Paginated list of resources in a module composite."""
    inp = ModuleResourcesInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    files = _module_root_to_filenames(installation, inp.module_root)
    if not files:
        return json_content({"count": 0, "offset": 0, "items": [], "has_more": False, "next_offset": None})
    all_resources: list[Any] = []
    for f in files:
        for res in installation.module_resources(f):
            all_resources.append({
                "resref": res.resname(),
                "type": res.restype().name,
                "extension": res.restype().extension,
                "size": res.size(),
                "source_file": f,
            })
    offset = inp.offset
    limit = inp.limit
    items = all_resources[offset : offset + limit]
    has_more = len(all_resources) > offset + limit
    next_offset = offset + len(items) if has_more else None
    return json_content({
        "count": len(items),
        "total": len(all_resources),
        "offset": offset,
        "items": items,
        "has_more": has_more,
        "next_offset": next_offset,
    })

