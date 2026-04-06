"""Format conversion tools: read_gff, read_2da, read_tlk (and later kotor_convert_resource)."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from mcp import types
from pykotor.extract.installation import SearchLocation
from pykotor.resource.formats.gff.gff_auto import read_gff
from pykotor.resource.formats.gff.gff_data import GFFList, GFFStruct
from pykotor.resource.formats.tlk.tlk_auto import read_tlk
from pykotor.resource.formats.twoda.twoda_auto import read_2da
from pykotor.resource.type import ResourceType

from kotormcp.schemas.inputs import Read2daInput, ReadGffInput, ReadTlkInput
from kotormcp.state import load_installation, resolve_game
from kotormcp.utils.formatting import json_content


def _gff_struct_to_dict(
    struct: GFFStruct,
    max_depth: int | None,
    max_fields: int | None,
    depth: int,
    field_count: list[int],
) -> dict[str, Any]:
    """Recursively convert GFF struct to JSON-serializable dict."""
    out: dict[str, Any] = {}
    for label, field_type, value in struct:
        if max_fields is not None and field_count[0] >= max_fields:
            out["_truncated"] = True
            break
        key = label or "__unnamed__"
        if value is None:
            out[key] = None
        elif isinstance(value, GFFList):
            if max_depth is not None and depth + 1 > max_depth:
                out[key] = f"<list[{len(value)} items, max_depth reached>"
            else:
                out[key] = []
                for item in value:
                    if max_fields is not None and field_count[0] >= max_fields:
                        out[key].append("...")
                        break
                    out[key].append(_gff_struct_to_dict(item, max_depth, max_fields, depth + 1, field_count))
            field_count[0] += 1
        elif isinstance(value, GFFStruct):  # nested struct
            if max_depth is not None and depth + 1 > max_depth:
                out[key] = "<struct, max_depth reached>"
            else:
                out[key] = _gff_struct_to_dict(value, max_depth, max_fields, depth + 1, field_count)
            field_count[0] += 1
        elif isinstance(value, bytes):
            out[key] = f"<bytes:{len(value)}>"
            field_count[0] += 1
        else:
            out[key] = value
            field_count[0] += 1
    return out


def get_tools() -> list[types.Tool]:
    """Return tool definitions for format conversion (read-only)."""
    return [
        types.Tool(
            name="kotor_read_gff",
            description="Use when you need the full GFF tree as JSON (DLG, UTC, ARE, etc.). Use field_paths or max_depth/max_fields to stay under response limits. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "resref": {"type": "string", "description": "Resource reference name"},
                    "restype": {"type": "string", "description": "Resource type (e.g. DLG, UTC)"},
                    "field_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional field paths to include",
                    },
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Max nesting depth"},
                    "max_fields": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1000,
                        "description": "Max fields to return",
                    },
                },
                "required": ["game", "resref", "restype"],
            },
        ),
        types.Tool(
            name="kotor_read_2da",
            description="Use when you need a 2DA table as JSON with optional row range and column filter. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "resref": {"type": "string", "description": "2DA table resref (e.g. appearance)"},
                    "row_start": {"type": "integer", "minimum": 0, "description": "First row index"},
                    "row_end": {"type": "integer", "minimum": 0, "description": "Last row index (inclusive)"},
                    "columns": {"type": "array", "items": {"type": "string"}, "description": "Column names to include"},
                },
                "required": ["game", "resref"],
            },
        ),
        types.Tool(
            name="kotor_read_tlk",
            description="Use when you need TLK (dialog.tlk) entries by strref range or text search. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "strref_start": {"type": "integer", "minimum": 0, "description": "Start strref"},
                    "strref_end": {"type": "integer", "minimum": 0, "description": "End strref"},
                    "text_search": {"type": "string", "description": "Substring search in text"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 500,
                        "default": 100,
                        "description": "Max entries",
                    },
                },
                "required": ["game"],
            },
        ),
    ]


async def handle_read_gff(arguments: dict[str, Any]) -> types.CallToolResult:
    """Read GFF resource and return as JSON."""
    inp = ReadGffInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    order = [SearchLocation.OVERRIDE, SearchLocation.CUSTOM_FOLDERS, SearchLocation.MODULES, SearchLocation.CHITIN]
    restype = ResourceType.from_extension(inp.restype.lstrip(".").lower()) if inp.restype else ResourceType.GFF
    if restype == ResourceType.INVALID:
        restype = ResourceType.GFF
    result = installation.resource(inp.resref, restype, order=order)
    if result is None:
        raise ValueError(f"Resource {inp.resref}.{restype.extension} not found.")
    gff = read_gff(BytesIO(result.data))
    field_count: list[int] = [0]
    tree = _gff_struct_to_dict(
        gff.root,
        inp.max_depth,
        inp.max_fields,
        depth=0,
        field_count=field_count,
    )
    return json_content(
        {
            "resref": inp.resref,
            "restype": restype.name,
            "root": tree,
            "truncated": field_count[0] >= (inp.max_fields or 0) if inp.max_fields else False,
        }
    )


async def handle_read_2da(arguments: dict[str, Any]) -> types.CallToolResult:
    """Read 2DA table with optional row/column slice."""
    inp = Read2daInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    order = [SearchLocation.OVERRIDE, SearchLocation.MODULES, SearchLocation.CHITIN]
    result = installation.resource(inp.resref, ResourceType.TwoDA, order=order)
    if result is None:
        raise ValueError(f"2DA {inp.resref} not found.")
    table = read_2da(BytesIO(result.data))
    headers = table.get_headers()
    if inp.columns:
        headers = [h for h in headers if h in inp.columns]
    row_start = inp.row_start or 0
    row_end = inp.row_end if inp.row_end is not None else table.get_height()
    row_end = min(row_end, table.get_height())
    rows: list[dict[str, str]] = []
    for i in range(row_start, row_end):
        row_dict: dict[str, str] = {}
        for h in headers:
            row_dict[h] = table.get_cell_safe(i, h, "")
        rows.append(row_dict)
    return json_content(
        {
            "resref": inp.resref,
            "columns": headers,
            "row_count": len(rows),
            "row_start": row_start,
            "rows": rows,
        }
    )


async def handle_read_tlk(arguments: dict[str, Any]) -> types.CallToolResult:
    """Read TLK entries by strref range or text search."""
    inp = ReadTlkInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    result = installation.resource("dialog", ResourceType.TLK, order=[SearchLocation.OVERRIDE, SearchLocation.CHITIN])
    if result is None:
        raise ValueError("dialog.tlk not found in installation.")
    tlk = read_tlk(BytesIO(result.data))
    entries_out: list[dict[str, Any]] = []
    limit = inp.limit
    if inp.text_search:
        search_lower = inp.text_search.lower()
        for strref, entry in enumerate(tlk.entries):
            if len(entries_out) >= limit:
                break
            if search_lower in entry.text.lower():
                entries_out.append({"strref": strref, "text": entry.text[:500], "sound": str(entry.voiceover)})
    else:
        start = inp.strref_start or 0
        end = inp.strref_end if inp.strref_end is not None else len(tlk.entries)
        end = min(end, len(tlk.entries))
        for strref in range(start, min(start + limit, end)):
            if strref < len(tlk.entries):
                entry = tlk.entries[strref]
                entries_out.append({"strref": strref, "text": entry.text[:500], "sound": str(entry.voiceover)})
    return json_content(
        {
            "language": tlk.language.name,
            "total_entries": len(tlk.entries),
            "count": len(entries_out),
            "entries": entries_out,
        }
    )
