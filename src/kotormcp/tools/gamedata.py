"""Game data tools: journal overview, lookup_2da, lookup_tlk."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any

from mcp import types
from pykotor.extract.installation import SearchLocation
from pykotor.resource.formats.gff.gff_auto import read_gff
from pykotor.resource.formats.twoda.twoda_auto import read_2da
from pykotor.resource.type import ResourceType

from kotormcp.schemas.inputs import JournalOverviewInput, Lookup2daInput, LookupTlkInput
from kotormcp.state import load_installation, resolve_game
from kotormcp.utils.formatting import json_content

if TYPE_CHECKING:
    from pykotor.extract.installation import Installation


def _journal_entries(installation: Installation) -> list[dict[str, Any]]:
    """Parse global.jrl and extract plot entries (structure documented in xoreos journal.cpp)."""
    resource = installation.resource("global", ResourceType.JRL, order=[SearchLocation.OVERRIDE, SearchLocation.MODULES, SearchLocation.CHITIN])
    if resource is None:
        msg = "Unable to locate global.jrl in the current installation."
        raise ValueError(msg)
    gff = read_gff(BytesIO(resource.data))
    categories = []
    for entry in gff.root.get_list("Categories", default=[]):
        category = {
            "name": entry.get_string("Name", ""),
            "tag": entry.get_string("Tag", ""),
            "comment": entry.get_string("Comment", ""),
            "priority": entry.get_uint("Priority", 0),
            "xp": entry.get_uint("XP", 0),
            "entries": [],
        }
        for quest in entry.get_list("EntryList", default=[]):
            category["entries"].append(
                {
                    "id": quest.get_uint("ID", 0),
                    "text": quest.get_string("Text", "")[:400],
                    "comment": quest.get_string("Comment", ""),
                    "completes_plot": bool(quest.get_uint("End", 0)),
                },
            )
        categories.append(category)
    return categories


def get_tools() -> list[types.Tool]:
    """Return tool definitions for game data."""
    return [
        types.Tool(
            name="journalOverview",
            description="Use when you need a summary of global.jrl plot categories and entries for the installation. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {"game": {"type": "string", "description": "Game alias: k1 or k2"}},
                "required": ["game"],
            },
        ),
        types.Tool(
            name="kotor_lookup_2da",
            description="Use when you need to query a 2DA table by row index, column name, or value search. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game": {"type": "string", "description": "Game alias: k1 or k2"},
                    "table_name": {"type": "string", "description": "2DA table resref"},
                    "row_index": {"type": "integer", "minimum": 0, "description": "Row index"},
                    "column": {"type": "string", "description": "Column name to filter or return"},
                    "value_search": {"type": "string", "description": "Search value in a column"},
                },
                "required": ["game", "table_name"],
            },
        ),
        types.Tool(
            name="kotor_lookup_tlk",
            description="Use when you need to resolve a strref to display text from dialog.tlk. Read-only.",
            inputSchema={
                "type": "object",
                "properties": {"game": {"type": "string", "description": "Game alias: k1 or k2"}, "strref": {"type": "integer", "description": "TLK string reference ID"}},
                "required": ["game", "strref"],
            },
        ),
    ]


async def handle_journal_overview(arguments: dict[str, Any]) -> types.CallToolResult:
    """Return journal/plot overview from global.jrl."""
    inp = JournalOverviewInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        msg = "Specify game parameter (k1/k2)."
        raise ValueError(msg)
    installation = load_installation(game)
    payload = _journal_entries(installation)
    return json_content({"count": len(payload), "categories": payload})


async def handle_lookup_2da(arguments: dict[str, Any]) -> types.CallToolResult:
    """Query 2DA table by row index or value search."""
    inp = Lookup2daInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    order = [SearchLocation.OVERRIDE, SearchLocation.MODULES, SearchLocation.CHITIN]
    result = installation.resource(inp.table_name, ResourceType.TwoDA, order=order)
    if result is None:
        raise ValueError(f"2DA table '{inp.table_name}' not found.")
    table = read_2da(BytesIO(result.data))
    if inp.row_index is not None:
        row = table.get_row(inp.row_index)
        if row is None:
            raise ValueError(f"Row index {inp.row_index} out of range.")
        out = {h: table.get_cell_safe(inp.row_index, h, "") for h in table.get_headers()}
        return json_content({"table": inp.table_name, "row_index": inp.row_index, "row": out})
    if inp.value_search and inp.column:
        matches = []
        for i in range(table.get_height()):
            val = table.get_cell_safe(i, inp.column, "")
            if inp.value_search.lower() in val.lower():
                matches.append({"row_index": i, inp.column: val})
                if len(matches) >= 50:
                    break
        return json_content({"table": inp.table_name, "column": inp.column, "value_search": inp.value_search, "matches": matches})
    return json_content({"table": inp.table_name, "columns": table.get_headers(), "row_count": table.get_height()})


async def handle_lookup_tlk(arguments: dict[str, Any]) -> types.CallToolResult:
    """Resolve strref to text from dialog.tlk."""
    inp = LookupTlkInput.model_validate(arguments)
    game = resolve_game(inp.game)
    if game is None:
        raise ValueError("Specify game (k1/k2).")
    installation = load_installation(game)
    text = installation.talktable().string(inp.strref)
    return json_content({"strref": inp.strref, "text": text})
