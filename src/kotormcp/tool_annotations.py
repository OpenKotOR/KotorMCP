"""Intended MCP tool annotations (readOnlyHint, destructiveHint, etc.).

When the MCP Python SDK supports tool annotations (see modelcontextprotocol/spec
and microsoft/mcp#222), add these to each Tool() so hosts can show confirmations
for destructive tools and skip them for read-only tools.

- readOnlyHint: True = no side effects; no confirmation needed.
- destructiveHint: True = may write/delete (e.g. kotor_extract_resource).
- idempotentHint: True = repeated same call has no extra effect.
- openWorldHint: True = interacts with external state (here: disk/installation).
"""

# Tool name -> intended annotations (for future SDK support)
TOOL_ANNOTATIONS: dict[str, dict[str, bool]] = {
    "detectInstallations": {"readOnlyHint": True, "idempotentHint": True},
    "loadInstallation": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_installation_info": {"readOnlyHint": True, "idempotentHint": True},
    "listResources": {"readOnlyHint": True, "idempotentHint": True},
    "describeResource": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_find_resource": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_search_resources": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_read_gff": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_read_2da": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_read_tlk": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_list_modules": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_describe_module": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_module_resources": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_list_archive": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_extract_resource": {"destructiveHint": True, "openWorldHint": True},
    "journalOverview": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_lookup_2da": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_lookup_tlk": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_list_references": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_find_referrers": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_find_strref_referrers": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_describe_dlg": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_describe_jrl": {"readOnlyHint": True, "idempotentHint": True},
    "kotor_describe_resource_refs": {"readOnlyHint": True, "idempotentHint": True},
}
