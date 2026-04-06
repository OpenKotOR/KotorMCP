"""Pydantic v2 input models for MCP tool arguments."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoadInstallationInput(BaseModel):
    """Input for loadInstallation tool."""

    game: str = Field(..., description="Game alias: k1, k2, or tsl")
    path: str | None = Field(None, description="Optional absolute path to installation")


class ListResourcesInput(BaseModel):
    """Input for listResources tool. Field names match MCP tool schema (camelCase)."""

    game: str = Field(..., description="Game alias: k1 or k2")
    location: str = Field(
        default="all",
        description="override, modules, module:<name>, core, texturepacks, streammusic, etc.",
    )
    moduleFilter: str | None = Field(None, description="Substring filter for module names")  # noqa: N815
    resourceTypes: list[str] | None = Field(None, description="Resource types (NCS, DLG, JRL, .gff, etc.)")  # noqa: N815
    resrefQuery: str | None = Field(None, description="Case-insensitive substring filter for resrefs")  # noqa: N815
    limit: int = Field(default=50, ge=1, le=500, description="Max results per page")
    offset: int = Field(default=0, ge=0, description="Skip first N results (pagination)")


class DescribeResourceInput(BaseModel):
    """Input for describeResource tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="Resource reference name")
    restype: str = Field(..., description="Resource type (extension or name)")
    order: list[str] | None = Field(
        None,
        description="Optional SearchLocation names (OVERRIDE, MODULES, CHITIN, ...)",
    )


class JournalOverviewInput(BaseModel):
    """Input for journalOverview tool."""

    game: str = Field(..., description="Game alias: k1 or k2")


class Lookup2daInput(BaseModel):
    """Input for kotor_lookup_2da tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    table_name: str = Field(..., description="2DA table name (e.g. appearance, baseitems)")
    row_index: int | None = Field(None, ge=0, description="Row index to fetch")
    column: str | None = Field(None, description="Column name to filter or return")
    value_search: str | None = Field(None, description="Search for rows where column contains this value")


class LookupTlkInput(BaseModel):
    """Input for kotor_lookup_tlk tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    strref: int = Field(..., ge=-1, description="String reference ID")


class FindResourceInput(BaseModel):
    """Input for kotor_find_resource tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    query: str = Field(
        ..., description="Resource name with optional extension (e.g. 203tell.wok) or glob (e.g. 203tel*)"
    )
    order: list[str] | None = Field(
        None, description="Comma-separated SearchLocation names; default: canonical resolution order"
    )
    all_locations: bool = Field(
        default=True, description="If True, return all locations with priority; if False, only selected per resource"
    )


class SearchResourcesInput(BaseModel):
    """Input for kotor_search_resources tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    pattern: str = Field(..., description="Regex pattern to match resource names (resref)")
    location: str = Field(default="all", description="override, modules, chitin, etc.")
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ListModulesInput(BaseModel):
    """Input for kotor_list_modules tool."""

    game: str = Field(..., description="Game alias: k1 or k2")


class DescribeModuleInput(BaseModel):
    """Input for kotor_describe_module tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    module_root: str = Field(..., description="Module root name (e.g. 003ebo, danm13)")


class ModuleResourcesInput(BaseModel):
    """Input for kotor_module_resources tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    module_root: str = Field(..., description="Module root name (e.g. 003ebo)")
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ListArchiveInput(BaseModel):
    """Input for kotor_list_archive tool."""

    file_path: str = Field(..., description="Path to archive (KEY, BIF, RIM, ERF, MOD)")
    key_file: str | None = Field(None, description="Path to KEY file (for BIF listing)")
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ExtractResourceInput(BaseModel):
    """Input for kotor_extract_resource tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="Resource reference name")
    restype: str = Field(..., description="Resource type (extension or name)")
    output_path: str = Field(..., description="Output file or directory path")
    source: str | None = Field(
        None,
        description="Extract only from this location (e.g. OVERRIDE, CHITIN, MODULES). Omit for first match in canonical order",
    )


class ReadGffInput(BaseModel):
    """Input for kotor_read_gff tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="Resource reference name")
    restype: str = Field(..., description="Resource type (e.g. GFF, UTC, DLG)")
    field_paths: list[str] | None = Field(None, description="Optional field paths to include; omit for full tree")
    max_depth: int | None = Field(None, ge=1, le=20, description="Max traversal depth")
    max_fields: int | None = Field(None, ge=1, le=1000, description="Max number of fields to return")


class Read2daInput(BaseModel):
    """Input for kotor_read_2da tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="2DA table name (e.g. appearance, baseitems)")
    row_start: int | None = Field(None, ge=0, description="First row index (inclusive)")
    row_end: int | None = Field(None, ge=0, description="Last row index (exclusive)")
    columns: list[str] | None = Field(None, description="Column names to include; omit for all")


class ReadTlkInput(BaseModel):
    """Input for kotor_read_tlk tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    strref_start: int | None = Field(None, ge=0, description="First strref (inclusive)")
    strref_end: int | None = Field(None, ge=0, description="Last strref (exclusive)")
    text_search: str | None = Field(None, description="Substring search in text; returns matching entries")
    limit: int = Field(default=100, ge=1, le=500)


class ListReferencesInput(BaseModel):
    """Input for kotor_list_references tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="Resource reference name (e.g. my_dlg)")
    restype: str = Field(..., description="Resource type (e.g. DLG, UTC, GFF)")
    path: str | None = Field(None, description="Optional installation path override")


class FindReferrersInput(BaseModel):
    """Input for kotor_find_referrers tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    value: str = Field(..., description="Script resref, tag, conversation resref, or generic resref to find")
    reference_kind: str = Field(
        default="resref",
        description="script | tag | conversation | resref",
    )
    path: str | None = Field(None, description="Optional installation path override")
    module_root: str | None = Field(None, description="Limit to resources from this module (e.g. danm13)")
    partial_match: bool = Field(default=False, description="Allow partial matches")
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class FindStrrefReferrersInput(BaseModel):
    """Input for kotor_find_strref_referrers tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    strref: int = Field(..., ge=0, description="TLK string reference ID to find")
    path: str | None = Field(None, description="Optional installation path override")
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class DescribeDlgInput(BaseModel):
    """Input for kotor_describe_dlg tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="DLG resource name")
    path: str | None = Field(None, description="Optional installation path override")


class DescribeJrlInput(BaseModel):
    """Input for kotor_describe_jrl tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="JRL (journal) resource name")
    path: str | None = Field(None, description="Optional installation path override")


class DescribeResourceRefsInput(BaseModel):
    """Input for kotor_describe_resource_refs tool."""

    game: str = Field(..., description="Game alias: k1 or k2")
    resref: str = Field(..., description="Resource reference name")
    restype: str = Field(..., description="Resource type (e.g. DLG, UTC, GFF)")
    path: str | None = Field(None, description="Optional installation path override")
