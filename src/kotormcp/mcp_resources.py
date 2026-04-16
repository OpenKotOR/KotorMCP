"""MCP resources: kotor:// URI scheme for passive context injection.

URIs:
  kotor://k1/resource/{resref}.{ext}   - Resolved via installation (resolution order)
  kotor://k2/resource/{resref}.{ext}
  kotor://k1/2da/{table_name}          - 2DA table as JSON
  kotor://k2/2da/{table_name}
  kotor://k1/tlk/{strref}              - TLK string by reference
  kotor://k2/tlk/{strref}
  kotor://k1/override/                 - Override directory listing (template)
  kotor://k2/override/
  kotor://k1/walkmesh-diagram/{resref}.wok  - Text validation diagram for walkmesh (perimeter, transitions)
  kotor://k2/walkmesh-diagram/{resref}.wok
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import unquote

from pykotor.common.misc import Game
from pykotor.resource.type import ResourceType

from kotormcp.state import load_installation, resolve_game


def _game_from_uri_authority(authority: str) -> Game | None:
    """Map URI authority (host) to Game."""
    return resolve_game("k1" if authority == "k1" else "k2" if authority == "k2" else None)


def parse_kotor_uri(uri: str) -> dict[str, Any] | None:
    """Parse kotor:// URI into components. Returns dict with game, type, path, authority, etc. or None if invalid."""
    if not uri.startswith("kotor://"):
        return None
    parts = uri[8:].split("/", 2)  # after "kotor://"
    if len(parts) < 2:
        return None
    authority, resource_type = parts[0].lower(), parts[1].lower()
    path = unquote(parts[2]) if len(parts) > 2 else ""
    game = _game_from_uri_authority(authority)
    if game is None and authority != "docs":
        return None
    return {"game": game, "type": resource_type, "path": path, "uri": uri, "authority": authority}


async def list_resources() -> list[dict[str, Any]]:
    """Return list of MCP resource templates (kotor:// URIs) for discovery.

    Returns static template URIs; clients request actual content via read_resource.
    """
    return [
        {
            "uri": "kotor://k1/resource/{resref}.{ext}",
            "name": "K1 Resource",
            "description": "Resolve resource by resref.ext (resolution order)",
            "mimeType": "application/octet-stream",
        },
        {
            "uri": "kotor://k2/resource/{resref}.{ext}",
            "name": "K2 Resource",
            "description": "Resolve resource by resref.ext (resolution order)",
            "mimeType": "application/octet-stream",
        },
        {
            "uri": "kotor://k1/2da/{table_name}",
            "name": "K1 2DA Table",
            "description": "2DA table as JSON",
            "mimeType": "application/json",
        },
        {
            "uri": "kotor://k2/2da/{table_name}",
            "name": "K2 2DA Table",
            "description": "2DA table as JSON",
            "mimeType": "application/json",
        },
        {
            "uri": "kotor://k1/tlk/{strref}",
            "name": "K1 TLK String",
            "description": "TLK string by strref",
            "mimeType": "text/plain",
        },
        {
            "uri": "kotor://k2/tlk/{strref}",
            "name": "K2 TLK String",
            "description": "TLK string by strref",
            "mimeType": "text/plain",
        },
        {
            "uri": "kotor://k1/walkmesh-diagram/{resref}.wok",
            "name": "K1 Walkmesh validation diagram",
            "description": "Text validation diagram (perimeter, transitions) for area walkmesh",
            "mimeType": "text/plain",
        },
        {
            "uri": "kotor://k2/walkmesh-diagram/{resref}.wok",
            "name": "K2 Walkmesh validation diagram",
            "description": "Text validation diagram (perimeter, transitions) for area walkmesh",
            "mimeType": "text/plain",
        },
        {
            "uri": "kotor://docs/capabilities",
            "name": "KotorMCP capabilities",
            "description": "Resolution order, tool index, and when to use each tool (agent onboarding)",
            "mimeType": "text/markdown",
        },
    ]


def _get_capabilities_doc() -> str:
    """One-page onboarding: resolution order, tool index, when to use."""
    return """# KotorMCP capabilities

## Resource resolution order

Resources are resolved in this order (first match wins):

1. **OVERRIDE** — Game override directory (user/mod content)
2. **MODULES** — Module ERFs (e.g. 003ebo.erf) in load order
3. **CHITIN** — Base game chitin.key / data

Use optional `source` on `kotor_extract_resource` (or `--source` on `pykotor get`) to read from a single location (e.g. CHITIN only).

## Tool index

| Tool | Use when |
|------|----------|
| openInstallation | Build or reuse a compacted in-memory installation snapshot and get a snapshot handle |
| getInstallationSnapshot | Page through a snapshot handle and optionally include compacted per-resource documents |
| kotor_installation_info | Check game path, validity, module/override counts |
| kotor_find_resource | Find files by resref/glob (e.g. `*.dlg`) before reading |
| kotor_search_resources | Search by type/location with pagination |
| kotor_extract_resource | Extract binary to disk (use `source` to restrict location) |
| kotor_list_archive | List contents of an ERF/BIF |
| kotor_list_modules | List modules (areas) in the installation |
| kotor_describe_module | Module metadata and dependencies |
| kotor_module_resources | Resources inside a module |
| kotor_read_gff | Read GFF (DLG, UTC, etc.) as JSON |
| kotor_read_2da | Read 2DA table as JSON |
| kotor_read_tlk | Resolve TLK string by strref |
| kotor_lookup_2da | Look up 2DA row by column value |
| kotor_lookup_tlk | Look up TLK by substring (returns strref + text) |
| kotor_list_references | List script/DLG/plot refs in a resource |
| kotor_find_referrers | Find resources that reference a resref |
| kotor_find_strref_referrers | Find resources that use a TLK strref |
| kotor_describe_dlg | DLG structure and entry/reply links |
| kotor_describe_jrl | Journal structure |
| kotor_describe_resource_refs | Reference summary for any resource |
| kotor_walkmesh_validation_diagram | Text validation diagram for walkmesh (perimeter, transitions; quality context for agents) |

Tools that write to disk: kotor_extract_resource. Paths are validated (allowlist, no traversal).
"""


async def read_resource(uri: str) -> dict[str, Any]:  # noqa: PLR0915
    """Read kotor:// resource and return content (text or base64 blob)."""
    parsed = parse_kotor_uri(uri)
    if not parsed:
        msg = f"Invalid kotor:// URI: {uri}"
        raise ValueError(msg)
    authority = parsed.get("authority", "")
    resource_type = parsed["type"]
    path = parsed["path"]
    if authority == "docs" and resource_type == "capabilities":
        return {"uri": uri, "mimeType": "text/markdown", "text": _get_capabilities_doc()}
    game = parsed["game"]
    if game is None:
        msg = f"Invalid kotor:// URI: {uri}"
        raise ValueError(msg)
    installation = load_installation(game)
    if resource_type == "resource":
        # path = resref.ext  # noqa: ERA001
        from pykotor.extract.file import ResourceIdentifier  # noqa: PLC0415
        from pykotor.extract.installation import SearchLocation  # noqa: PLC0415
        from pykotor.tools.finder import canonical_search_order  # noqa: PLC0415

        ident = ResourceIdentifier.from_path(path)
        if ident.restype == ResourceType.INVALID:
            msg = f"Unknown resource type in URI path: {path}"
            raise ValueError(msg)
        order = canonical_search_order()
        result = installation.resource(ident.resname, ident.restype, order=order)
        if result is None:
            msg = f"Resource not found: {path}"
            raise ValueError(msg)
        return {
            "uri": uri,
            "mimeType": "application/octet-stream",
            "blob": base64.b64encode(result.data).decode("ascii"),
        }
    if resource_type == "2da":
        from io import BytesIO  # noqa: PLC0415

        from pykotor.extract.installation import SearchLocation  # noqa: PLC0415
        from pykotor.resource.formats.twoda.twoda_auto import read_2da  # noqa: PLC0415

        table_name = path.strip() or "appearance"
        order = [SearchLocation.OVERRIDE, SearchLocation.MODULES, SearchLocation.CHITIN]
        result = installation.resource(table_name, ResourceType.TwoDA, order=order)
        if result is None:
            msg = f"2DA table not found: {table_name}"
            raise ValueError(msg)
        table = read_2da(BytesIO(result.data))
        headers = table.get_headers()
        rows = []
        for i in range(min(table.get_height(), 500)):
            rows.append({h: table.get_cell_safe(i, h, "") for h in headers})
        data = {"columns": headers, "row_count": table.get_height(), "rows": rows}
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, indent=2)}
    if resource_type == "tlk":
        strref = int(path.strip()) if path.strip().isdigit() else -1
        text = installation.talktable().string(strref)
        return {"uri": uri, "mimeType": "text/plain", "text": text}
    if resource_type == "walkmesh-diagram":
        from io import BytesIO  # noqa: PLC0415

        from pykotor.extract.installation import SearchLocation  # noqa: PLC0415
        from pykotor.resource.formats.bwm import read_bwm  # noqa: PLC0415
        from pykotor.tools.walkmesh_render_diagram import render_bwm_validation_diagram_lines  # noqa: PLC0415

        resref = path.strip().lower().removesuffix(".wok") or path.strip()
        order = [SearchLocation.OVERRIDE, SearchLocation.CUSTOM_FOLDERS, SearchLocation.MODULES, SearchLocation.CHITIN]
        result = installation.resource(resref, ResourceType.WOK, order=order)
        if result is None:
            msg = f"Walkmesh {resref}.wok not found"
            raise ValueError(msg)
        bwm = read_bwm(BytesIO(result.data))
        lines = render_bwm_validation_diagram_lines(bwm, use_color=False)
        return {"uri": uri, "mimeType": "text/plain", "text": "\n".join(lines)}
    msg = f"Unsupported resource type in URI: {resource_type}"
    raise ValueError(msg)
