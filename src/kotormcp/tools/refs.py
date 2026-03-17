"""Scripts, references, and plot tools: list refs, find referrers, describe DLG/JRL."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from mcp import types
from pykotor.resource.formats.gff import read_gff
from pykotor.resource.formats.gff.gff_data import GFFList
from pykotor.resource.type import ResourceType
from pykotor.tools.finder import canonical_search_order
from pykotor.tools.reference_finder import find_field_value_references
from pykotor.tools.references import extract_references, find_referrers

from kotormcp.schemas.inputs import (
    DescribeDlgInput,
    DescribeJrlInput,
    DescribeResourceRefsInput,
    FindReferrersInput,
    FindStrrefReferrersInput,
    ListReferencesInput,
)
from kotormcp.state import load_installation, resolve_game
from kotormcp.utils.formatting import json_content


def _parse_restype(restype: str) -> ResourceType:
    """Parse restype string to ResourceType."""
    value = restype.strip().upper()
    if value in ResourceType.__members__:
        return ResourceType[value]
    cleaned = value.lstrip(".").lower()
    return ResourceType.from_extension(cleaned)


def _order_default():
    return canonical_search_order()


def get_tools() -> list[types.Tool]:
    """Return tool definitions for references and plot (read-only)."""
    return [
        types.Tool(
            name="kotor_list_references",
            description="Use when tracing what a resource references: list outbound refs (scripts, conversations, tags, template resrefs) by field path. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "resref": {"type": "string", "description": "Resource reference name"},
                    "restype": {"type": "string", "description": "Resource type (e.g. DLG, UTC)"},
                    "path": {"type": "string", "description": "Optional installation path override"},
                },
                "required": ["game", "resref", "restype"],
            },
        ),
        types.Tool(
            name="kotor_find_referrers",
            description="Use when you need to find which resources reference a script resref, tag, conversation, or resref. Use module_root to narrow; expensive over full install. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "value": {"type": "string", "description": "Script resref, tag, conversation resref, or resref to search for"},
                    "reference_kind": {"type": "string", "enum": ["script", "tag", "conversation", "resref"], "default": "resref", "description": "Kind of reference"},
                    "path": {"type": "string", "description": "Optional installation path override"},
                    "module_root": {"type": "string", "description": "Limit search to this module"},
                    "partial_match": {"type": "boolean", "default": False, "description": "Allow substring match"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100, "description": "Max results"},
                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Pagination offset"},
                },
                "required": ["game", "value"],
            },
        ),
        types.Tool(
            name="kotor_find_strref_referrers",
            description="Use when you need to find which resources use a TLK strref (TLK/2DA Find References parity). Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "strref": {"type": "integer", "minimum": 0, "description": "TLK string reference ID"},
                    "path": {"type": "string", "description": "Optional installation path override"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100, "description": "Max results"},
                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Pagination offset"},
                },
                "required": ["game", "strref"],
            },
        ),
        types.Tool(
            name="kotor_describe_dlg",
            description="Use when you need DLG structure: entry/reply counts and script/condition refs. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "resref": {"type": "string", "description": "DLG resource reference"},
                    "path": {"type": "string", "description": "Optional installation path override"},
                },
                "required": ["game", "resref"],
            },
        ),
        types.Tool(
            name="kotor_describe_jrl",
            description="Use when you need a JRL (journal) summary: categories and entries. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "resref": {"type": "string", "description": "JRL resource reference (e.g. global)"},
                    "path": {"type": "string", "description": "Optional installation path override"},
                },
                "required": ["game", "resref"],
            },
        ),
        types.Tool(
            name="kotor_describe_resource_refs",
            description="Use when you need a reference summary for any GFF resource (scripts, conversations, tags, template resrefs). Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "resref": {"type": "string", "description": "Resource reference name"},
                    "restype": {"type": "string", "description": "Resource type (e.g. UTC, ARE)"},
                    "path": {"type": "string", "description": "Optional installation path override"},
                },
                "required": ["game", "resref", "restype"],
            },
        ),
    ]


async def handle_list_references(arguments: dict[str, Any]) -> types.CallToolResult:
    """List outbound references from a single GFF resource."""
    inp = ListReferencesInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1 or k2).")
    installation = load_installation(game, inp.path)
    restype = _parse_restype(inp.restype)
    if not restype.is_gff():
        raise ValueError(f"Resource type {inp.restype} is not a GFF type.")
    result = installation.resource(inp.resref, restype, order=_order_default())
    if result is None:
        raise ValueError(f"Resource {inp.resref}.{restype.extension} not found.")
    gff = read_gff(BytesIO(result.data))
    file_type = restype.extension.upper()
    refs = extract_references(gff, file_type)
    out = [{"ref_kind": r.ref_kind, "value": r.value, "field_path": r.field_path} for r in refs]
    return json_content({"resref": inp.resref, "restype": inp.restype, "references": out, "count": len(out)})


async def handle_find_referrers(arguments: dict[str, Any]) -> types.CallToolResult:
    """Find resources that reference the given value."""
    inp = FindReferrersInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1 or k2).")
    installation = load_installation(game, inp.path)
    kind = (inp.reference_kind or "resref").lower()
    if kind not in ("script", "tag", "conversation", "resref"):
        kind = "resref"
    results = find_referrers(
        installation,
        inp.value,
        reference_kind=kind,
        module_root=inp.module_root or None,
        partial_match=inp.partial_match,
        file_types=None,
    )
    total = len(results)
    start = min(inp.offset, total)
    end = min(start + inp.limit, total)
    page = results[start:end]
    items = [
        {
            "resref": r.file_resource.resname(),
            "restype": r.file_resource.restype().name,
            "field_path": r.field_path,
            "matched_value": r.matched_value,
            "filepath": str(r.file_resource.filepath()),
        }
        for r in page
    ]
    return json_content({
        "count": len(items),
        "offset": start,
        "total": total,
        "has_more": end < total,
        "items": items,
    })


async def handle_find_strref_referrers(arguments: dict[str, Any]) -> types.CallToolResult:
    """Find resources that reference a TLK strref (searches string form in GFF/2DA)."""
    inp = FindStrrefReferrersInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1 or k2).")
    installation = load_installation(game, inp.path)
    value = str(inp.strref)
    results = find_field_value_references(
        installation,
        value,
        partial_match=False,
        case_sensitive=True,
        file_pattern=None,
        file_types=None,
    )
    total = len(results)
    start = min(inp.offset, total)
    end = min(start + inp.limit, total)
    page = results[start:end]
    items = [
        {
            "resref": r.file_resource.resname(),
            "restype": r.file_resource.restype().name,
            "field_path": r.field_path,
            "matched_value": r.matched_value,
            "filepath": str(r.file_resource.filepath()),
        }
        for r in page
    ]
    return json_content({
        "count": len(items),
        "offset": start,
        "total": total,
        "has_more": end < total,
        "items": items,
    })


def _dlg_summary(gff: Any) -> dict[str, Any]:
    """Build a short DLG summary from root (entry/reply counts, script refs)."""
    root = gff.root
    entry_list = root.get("EntryList")
    reply_list = root.get("ReplyList")
    entry_count = len(entry_list) if isinstance(entry_list, GFFList) else 0
    reply_count = len(reply_list) if isinstance(reply_list, GFFList) else 0
    refs = extract_references(gff, "DLG")
    scripts = [r.value for r in refs if r.ref_kind == "script"]
    conversations = [r.value for r in refs if r.ref_kind == "conversation"]
    return {
        "entry_count": entry_count,
        "reply_count": reply_count,
        "script_refs": list(dict.fromkeys(scripts)),
        "conversation_refs": list(dict.fromkeys(conversations)),
        "reference_count": len(refs),
    }


def _jrl_summary(gff: Any) -> dict[str, Any]:
    """Build a short JRL summary (categories, entry count)."""
    root = gff.root
    categories = root.get("Categories")
    entries = root.get("EntryList")
    cat_count = len(categories) if isinstance(categories, GFFList) else 0
    entry_count = len(entries) if isinstance(entries, GFFList) else 0
    return {
        "category_count": cat_count,
        "entry_count": entry_count,
    }


async def handle_describe_dlg(arguments: dict[str, Any]) -> types.CallToolResult:
    """Describe a DLG resource (entries, replies, script/conversation refs)."""
    inp = DescribeDlgInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1 or k2).")
    installation = load_installation(game, inp.path)
    result = installation.resource(inp.resref, ResourceType.DLG, order=_order_default())
    if result is None:
        raise ValueError(f"DLG {inp.resref} not found.")
    gff = read_gff(BytesIO(result.data))
    summary = _dlg_summary(gff)
    summary["resref"] = inp.resref
    return json_content(summary)


async def handle_describe_jrl(arguments: dict[str, Any]) -> types.CallToolResult:
    """Describe a JRL resource (categories, entries)."""
    inp = DescribeJrlInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1 or k2).")
    installation = load_installation(game, inp.path)
    result = installation.resource(inp.resref, ResourceType.JRL, order=_order_default())
    if result is None:
        raise ValueError(f"JRL {inp.resref} not found.")
    gff = read_gff(BytesIO(result.data))
    summary = _jrl_summary(gff)
    summary["resref"] = inp.resref
    return json_content(summary)


async def handle_describe_resource_refs(arguments: dict[str, Any]) -> types.CallToolResult:
    """Generic GFF reference summary (extract_references)."""
    inp = DescribeResourceRefsInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1 or k2).")
    installation = load_installation(game, inp.path)
    restype = _parse_restype(inp.restype)
    if not restype.is_gff():
        raise ValueError(f"Resource type {inp.restype} is not a GFF type.")
    result = installation.resource(inp.resref, restype, order=_order_default())
    if result is None:
        raise ValueError(f"Resource {inp.resref}.{restype.extension} not found.")
    gff = read_gff(BytesIO(result.data))
    file_type = restype.extension.upper()
    refs = extract_references(gff, file_type)
    out = [{"ref_kind": r.ref_kind, "value": r.value, "field_path": r.field_path} for r in refs]
    return json_content({"resref": inp.resref, "restype": inp.restype, "references": out, "count": len(out)})
