"""Resource discovery tools: list, describe, find, search."""

from __future__ import annotations

import re
from io import BytesIO
from typing import TYPE_CHECKING, Any

from mcp import types
from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff.gff_auto import read_gff
from pykotor.resource.formats.tlk.tlk_auto import read_tlk
from pykotor.resource.formats.twoda.twoda_auto import read_2da
from pykotor.resource.type import ResourceType
from pykotor.tools.finder import canonical_search_order, find_resource

from kotormcp.schemas.inputs import DescribeResourceInput, FindResourceInput, ListResourcesInput, SearchResourcesInput
from kotormcp.state import load_installation, resolve_game
from kotormcp.utils.formatting import json_content

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from pykotor.extract.file import FileResource, ResourceResult

GFF_HEAVY_TYPES: frozenset[ResourceType] = frozenset(rt for rt in ResourceType if rt.is_gff())


def _parse_resource_types(raw: Iterable[str] | None) -> set[ResourceType]:
    if not raw:
        return set()
    parsed: set[ResourceType] = set()
    for token in raw:
        value = token.strip().upper()
        if not value:
            continue
        if value in ResourceType.__members__:
            parsed.add(ResourceType[value])
            continue
        cleaned = value.lstrip(".").lower()
        try:
            parsed.add(ResourceType.from_extension(cleaned))
        except ValueError:
            msg = f"Unknown resource type '{token}'"
            raise ValueError(msg) from None
    return parsed


def _resource_snapshot(source: str, resource: FileResource) -> dict[str, Any]:
    identifier = resource.identifier()
    return {
        "resref": identifier.lower_resname,
        "type": resource.restype().name,
        "extension": resource.restype().extension,
        "size": resource.size(),
        "source": source,
        "filepath": str(resource.filepath()),
        "inside_capsule": resource.inside_capsule,
        "inside_bif": resource.inside_bif,
    }


def _resolve_module_name(installation: Installation, alias: str) -> str | None:
    alias_lower = alias.lower()
    modules = installation.modules_list()
    lookup = {name.lower(): name for name in modules}
    if alias_lower in lookup:
        return lookup[alias_lower]
    for candidate in modules:
        if alias_lower in candidate.lower():
            return candidate
    return None


def _iter_resources_for_location(
    installation: Installation,
    location: str,
    module_filter: str | None,
) -> Iterator[tuple[str, FileResource]]:
    lowered = location.lower()
    if lowered == "auto":
        lowered = "all"
    if lowered in {"override", "all"}:
        for resource in installation.override_resources():
            yield "override", resource
    if lowered in {"core", "all"}:
        for resource in installation.core_resources():
            yield "core", resource
    if lowered.startswith("module:"):
        _, module_alias = lowered.split(":", 1)
        resolved = _resolve_module_name(installation, module_alias)
        if not resolved:
            return
        for resource in installation.module_resources(resolved):
            yield f"module:{resolved}", resource
        return
    if lowered in {"modules", "all"}:
        for module_name in installation.modules_list():
            if module_filter and module_filter.lower() not in module_name.lower():
                continue
            for resource in installation.module_resources(module_name):
                yield f"module:{module_name}", resource
    if lowered in {"chitin", "bif", "all"}:
        for resource in installation.chitin_resources():
            yield "chitin", resource
    if lowered in {"lips", "all"}:
        for filename in installation.lips_list():
            for resource in installation.lip_resources(filename):
                yield f"lips:{filename}", resource
    if lowered in {"texturepacks", "textures", "all"}:
        for filename in installation.texturepacks_list():
            for resource in installation.texturepack_resources(filename):
                yield f"texturepack:{filename}", resource
    if lowered in {"streammusic", "all"}:
        installation.load_streammusic()
        for resource in installation._streammusic:
            yield "streammusic", resource
    if lowered in {"streamsounds", "all"}:
        installation.load_streamsounds()
        for resource in installation._streamsounds:
            yield "streamsounds", resource
    if lowered in {"streamwaves", "voice", "all"}:
        installation.load_streamwaves()
        for resource in installation._streamwaves:
            yield "streamwaves", resource


def _summarize_gff(data: bytes) -> dict[str, Any]:
    gff = read_gff(BytesIO(data))
    root = gff.root
    fields: list[dict[str, Any]] = []
    for label, field_type, value in root:
        preview: Any = value
        if isinstance(value, bytes):
            preview = f"<bytes:{len(value)}>"
        elif hasattr(value, "__len__") and len(str(value)) > 120:
            preview = f"{str(value)[:117]}..."
        fields.append(
            {
                "label": label,
                "type": field_type.name,
                "preview": preview,
            },
        )
    return {
        "struct_id": root.struct_id,
        "field_count": len(root),
        "fields": fields[:20],
    }


def _summarize_tlk(data: bytes) -> dict[str, Any]:
    tlk = read_tlk(BytesIO(data))
    entries = []
    for strref, entry in list(tlk.strings.items())[:20]:
        entries.append(
            {
                "strref": strref,
                "text": entry.text[:200],
                "sound": entry.sound,
            },
        )
    return {"language": tlk.language.name, "entry_count": len(tlk.strings), "sample": entries}


def _summarize_2da(data: bytes) -> dict[str, Any]:
    table = read_2da(BytesIO(data))
    rows = []
    for idx, row in enumerate(table.rows):
        rows.append({"row": idx, "values": row})
        if idx >= 15:
            break
    return {"columns": table.headers, "row_count": len(table.rows), "sample": rows}


def _describe_resource(result: ResourceResult) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "resref": result.resname,
        "type": result.restype.name,
        "extension": result.restype.extension,
        "bytes": len(result.data),
        "source": str(result.filepath),
    }
    data = result.data
    if result.restype in GFF_HEAVY_TYPES:
        summary["analysis"] = _summarize_gff(data)
    elif result.restype == ResourceType.TLK:
        summary["analysis"] = _summarize_tlk(data)
    elif result.restype == ResourceType.TwoDA:
        summary["analysis"] = _summarize_2da(data)
    else:
        summary["analysis"] = {"size": len(data), "head": data[:64].hex()}
    return summary


def get_tools() -> list[types.Tool]:
    """Return tool definitions for resource discovery (read-only)."""
    return [
        types.Tool(
            name="listResources",
            description="Use when exploring installation contents: list resources from override/modules/chitin with optional filters. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "k1 or k2"},
                    "location": {
                        "type": "string",
                        "description": "override, modules, module:<name>, core, texturepacks, streammusic, etc.",
                    },
                    "moduleFilter": {"type": "string", "description": "Substring filter for module names."},
                    "resourceTypes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Resource types (NCS, DLG, JRL, .gff, etc.).",
                    },
                    "resrefQuery": {"type": "string", "description": "Case-insensitive substring filter for resrefs."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                    "offset": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                        "description": "Skip first N results (pagination)",
                    },
                },
            },
        ),
        types.Tool(
            name="describeResource",
            description="Use when you need a short summary of a resource (GFF, TLK, 2DA) using resolution order. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string"},
                    "resref": {"type": "string"},
                    "restype": {"type": "string"},
                    "order": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional SearchLocation names (OVERRIDE, MODULES, CHITIN, ...).",
                    },
                },
                "required": ["game", "resref", "restype"],
            },
        ),
        types.Tool(
            name="kotor_find_resource",
            description="Use when you need the first match for a resref or to see all locations. Supports glob (e.g. 203tel*). Resolution order: Override → MOD → KEY/BIF. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "k1 or k2"},
                    "query": {
                        "type": "string",
                        "description": "Resource name with optional extension (e.g. 203tell.wok) or glob (e.g. 203tel*)",
                    },
                    "order": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional SearchLocation order (OVERRIDE, MODULES, CHITIN, ...)",
                    },
                    "all_locations": {
                        "type": "boolean",
                        "description": "If true, return all locations with priority; if false, only selected per resource",
                        "default": True,
                    },
                },
                "required": ["game", "query"],
            },
        ),
        types.Tool(
            name="kotor_search_resources",
            description="Use when you need to search resource names by regex. Paginated; prefer location/type filter on large installs. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string"},
                    "pattern": {"type": "string", "description": "Regex pattern to match resref"},
                    "location": {
                        "type": "string",
                        "default": "all",
                        "description": "Filter by location (override, modules, core, etc.)",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 500,
                        "default": 50,
                        "description": "Max results per page",
                    },
                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Skip first N results"},
                },
                "required": ["game", "pattern"],
            },
        ),
    ]


async def handle_list_resources(arguments: dict[str, Any]) -> types.CallToolResult:
    """List resources with optional location/type/resref filters."""
    inp = ListResourcesInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game parameter (k1/k2)."
        raise ValueError(msg)
    installation = load_installation(game)
    location = inp.location
    module_filter = inp.moduleFilter
    type_filters = _parse_resource_types(inp.resourceTypes)
    resref_query = (inp.resrefQuery or "").lower()
    limit = inp.limit
    offset = inp.offset
    results: list[dict[str, Any]] = []
    skipped = 0
    for source, resource in _iter_resources_for_location(installation, location, module_filter):
        if resref_query and resref_query not in resource.resname().lower():
            continue
        if type_filters and resource.restype() not in type_filters:
            continue
        if skipped < offset:
            skipped += 1
            continue
        results.append(_resource_snapshot(source, resource))
        if len(results) >= limit:
            break
    has_more = len(results) == limit
    next_offset = (offset + len(results)) if has_more else None
    return json_content(
        {
            "count": len(results),
            "offset": offset,
            "items": results,
            "has_more": has_more,
            "next_offset": next_offset,
        }
    )


async def handle_describe_resource(arguments: dict[str, Any]) -> types.CallToolResult:
    """Fetch and summarize a single resource."""
    inp = DescribeResourceInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game parameter (k1/k2)."
        raise ValueError(msg)
    installation = load_installation(game)
    resref = inp.resref
    restype = inp.restype
    order = _parse_order_labels(
        inp.order
        or [
            SearchLocation.OVERRIDE.name,
            SearchLocation.CUSTOM_FOLDERS.name,
            SearchLocation.MODULES.name,
            SearchLocation.CHITIN.name,
        ],
    )
    resource_type = _parse_resource_types([restype]).pop()
    result = installation.resource(resref, resource_type, order=order)
    if result is None:
        msg = f"{resref}.{resource_type.extension} not found."
        raise ValueError(msg)
    summary = _describe_resource(result)
    return json_content(summary)


def _parse_order_labels(labels: list[str]) -> list[SearchLocation]:
    """Convert list of SearchLocation names to enum list."""
    order: list[SearchLocation] = []
    for label in labels:
        upper = label.upper()
        if upper not in SearchLocation.__members__:
            msg = f"Unknown SearchLocation '{label}'"
            raise ValueError(msg)
        order.append(SearchLocation[upper])
    return order


async def handle_find_resource(arguments: dict[str, Any]) -> types.CallToolResult:
    """Find resource(s) using strict resolution order; supports glob."""
    inp = FindResourceInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game parameter (k1/k2)."
        raise ValueError(msg)
    installation = load_installation(game)
    order = canonical_search_order()
    if inp.order:
        order = _parse_order_labels(inp.order)
    query = inp.query.strip()
    glob_pattern: str | None = None
    if "*" in query or "?" in query:
        glob_pattern = query
    results = find_resource(
        installation,
        resref=query if not glob_pattern else None,
        glob_pattern=glob_pattern,
        order=order,
        all_locations=inp.all_locations,
    )
    matches = [
        {
            "resref": r.resref,
            "type": r.restype.name,
            "extension": r.restype.extension,
            "size": r.size,
            "source": r.source.name,
            "filepath": str(r.filepath),
            "archive_path": r.archive_path,
            "archive_index": r.archive_index,
            "priority_index": r.priority_index,
            "is_selected": r.is_selected,
            "location_type": r.location_type,
        }
        for r in results
    ]
    return json_content({"count": len(matches), "matches": matches})


async def handle_search_resources(arguments: dict[str, Any]) -> types.CallToolResult:
    """Regex search over resource names; paginated."""
    inp = SearchResourcesInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game parameter (k1/k2)."
        raise ValueError(msg)
    installation = load_installation(game)
    try:
        pattern_re = re.compile(inp.pattern, re.IGNORECASE)
    except re.error as e:
        msg = f"Invalid regex pattern: {e}"
        raise ValueError(msg) from e
    items: list[dict[str, Any]] = []
    skipped = 0
    limit = inp.limit
    offset = inp.offset
    for source, resource in _iter_resources_for_location(installation, inp.location, None):
        if not pattern_re.search(resource.resname()):
            continue
        if skipped < offset:
            skipped += 1
            continue
        items.append(_resource_snapshot(source, resource))
        if len(items) >= limit:
            break
    has_more = len(items) == limit
    next_offset = (offset + len(items)) if has_more else None
    return json_content(
        {
            "total": len(items),
            "count": len(items),
            "offset": offset,
            "items": items,
            "has_more": has_more,
            "next_offset": next_offset,
        }
    )
