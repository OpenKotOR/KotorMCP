"""Tool registry: collect tool definitions and dispatch call_tool by name."""

from __future__ import annotations

from typing import Any

from mcp import types

from kotormcp.tools import archives, conversion, discovery, gamedata, installation, modules, refs, scripts, walkmesh, writing


def get_all_tools() -> list[types.Tool]:
    """Return all tool definitions from all tool modules."""
    return (
        installation.get_tools()
        + discovery.get_tools()
        + gamedata.get_tools()
        + archives.get_tools()
        + conversion.get_tools()
        + modules.get_tools()
        + refs.get_tools()
        + scripts.get_tools()
        + walkmesh.get_tools()
        + writing.get_tools()
    )


async def handle_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    """Dispatch tool invocation to the correct handler."""
    if name == "detectInstallations":
        return await installation.handle_detect_installations(arguments)
    if name == "loadInstallation":
        return await installation.handle_load_installation(arguments)
    if name == "kotor_installation_info":
        return await installation.handle_installation_info(arguments)
    if name == "listResources":
        return await discovery.handle_list_resources(arguments)
    if name == "describeResource":
        return await discovery.handle_describe_resource(arguments)
    if name == "kotor_find_resource":
        return await discovery.handle_find_resource(arguments)
    if name == "kotor_search_resources":
        return await discovery.handle_search_resources(arguments)
    if name == "kotor_read_gff":
        return await conversion.handle_read_gff(arguments)
    if name == "kotor_read_2da":
        return await conversion.handle_read_2da(arguments)
    if name == "kotor_read_tlk":
        return await conversion.handle_read_tlk(arguments)
    if name == "kotor_list_modules":
        return await modules.handle_list_modules(arguments)
    if name == "kotor_describe_module":
        return await modules.handle_describe_module(arguments)
    if name == "kotor_module_resources":
        return await modules.handle_module_resources(arguments)
    if name == "kotor_list_archive":
        return await archives.handle_list_archive(arguments)
    if name == "kotor_extract_resource":
        return await archives.handle_extract_resource(arguments)
    if name == "journalOverview":
        return await gamedata.handle_journal_overview(arguments)
    if name == "kotor_lookup_2da":
        return await gamedata.handle_lookup_2da(arguments)
    if name == "kotor_lookup_tlk":
        return await gamedata.handle_lookup_tlk(arguments)
    if name == "kotor_list_references":
        return await refs.handle_list_references(arguments)
    if name == "kotor_find_referrers":
        return await refs.handle_find_referrers(arguments)
    if name == "kotor_find_strref_referrers":
        return await refs.handle_find_strref_referrers(arguments)
    if name == "kotor_describe_dlg":
        return await refs.handle_describe_dlg(arguments)
    if name == "kotor_describe_jrl":
        return await refs.handle_describe_jrl(arguments)
    if name == "kotor_describe_resource_refs":
        return await refs.handle_describe_resource_refs(arguments)
    if name == "kotor_walkmesh_validation_diagram":
        return await walkmesh.handle_walkmesh_validation_diagram(arguments)
    msg = f"Unknown tool '{name}'"
    raise ValueError(msg)
