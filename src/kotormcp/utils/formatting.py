"""Response formatting: JSON content, truncation, pagination helpers."""

from __future__ import annotations

import json
from typing import Any

from mcp import types

# Recommended max response size for tool output; truncate with continuation hint when exceeded
MAX_RESPONSE_CHARS = 25_000


CONTINUATION_HINT = "Response exceeded character limit; use offset/limit or filters to request a smaller result."


def json_content(payload: Any, max_chars: int = MAX_RESPONSE_CHARS) -> types.CallToolResult:
    """Build MCP CallToolResult from a JSON-serializable payload.

    If serialized length exceeds max_chars, wraps in an object with truncated=True,
    continuation_hint, and truncated_preview (first N chars of serialized payload).
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])
    wrapper: dict[str, Any] = {
        "truncated": True,
        "continuation_hint": CONTINUATION_HINT,
        "truncated_preview": text[: max_chars - 200],
    }
    out = json.dumps(wrapper, ensure_ascii=False, indent=2)
    if len(out) > max_chars:
        out = out[: max_chars - 80] + "\n  ... (output truncated)"
    return types.CallToolResult(content=[types.TextContent(type="text", text=out)])
