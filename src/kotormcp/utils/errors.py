"""Error mapping and actionable messages for MCP tool responses."""

from __future__ import annotations

# Map common exceptions to actionable user-facing messages (plan §2.4).
# Tool handlers should raise ValueError with messages that state what went wrong and suggest
# a concrete next step (e.g. "Resource not found. Try: kotor_find_resource with a glob pattern.").
# Reserve technical details for --debug or logs.
