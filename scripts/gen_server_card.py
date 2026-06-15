#!/usr/bin/env python3
"""Regenerate the static MCP server-card from the live `tools/list`.

The card at `site/.well-known/mcp/server-card.json` is what registry probers and
non-interactive clients (Glama, Smithery) read instead of opening a session. It
must match what the running server actually advertises, so we generate it straight
from `edge.app.mcp_app.mcp.list_tools()` rather than hand-editing JSON.

Generate with `mcp>=1.12` (the edge runtime), which feeds docstrings through
`cleandoc` — so the emitted descriptions carry no leading-whitespace noise. The
gate checks below fail loudly if a regression (indent leak, missing output schema,
tautological description) slips back in; this is the repo's stand-in for a test.

Usage (from repo root, in a venv with edge/requirements.txt installed):

    EDGE_DEV_LOGIN_ENABLED=true PYTHONPATH=. python scripts/gen_server_card.py
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

# Importing edge.app.config builds Settings(); keep generation runnable offline by
# defaulting the dev flag (skips the strong-secret validator) when nothing is set.
os.environ.setdefault("EDGE_DEV_LOGIN_ENABLED", "true")

from edge.app import mcp_app  # noqa: E402

CARD_PATH = Path(__file__).resolve().parent.parent / "site" / ".well-known" / "mcp" / "server-card.json"
SERVER_VERSION = "0.2.0"


def _gate(tool) -> None:
    """Cheap TDQS hard-gate / smell checks — see docs/TDQS.md. Raise on regression."""
    desc = (tool.description or "").strip()
    title = tool.title or ""
    assert desc, f"{tool.name}: empty description (TDQS 'No Description' gate)"
    assert "\n    " not in (tool.description or ""), (
        f"{tool.name}: indent leak in description (regenerate with mcp>=1.12)"
    )
    assert desc.lower() not in {tool.name.lower(), title.lower()}, (
        f"{tool.name}: tautological description (equals name/title)"
    )
    assert tool.outputSchema, f"{tool.name}: missing output schema"


async def build_card() -> dict:
    tools = await mcp_app.mcp.list_tools()
    out = []
    for t in tools:
        _gate(t)
        out.append({
            "name": t.name,
            "title": t.title,
            "description": t.description,
            "inputSchema": t.inputSchema,
            "outputSchema": t.outputSchema,
            "annotations": t.annotations and t.annotations.model_dump(exclude_none=True),
        })
    return {
        "serverInfo": {"name": mcp_app.mcp.name, "version": SERVER_VERSION},
        # Discovery + read tools are open; only write tools require the OAuth Bearer.
        "authentication": {"required": False, "schemes": ["oauth2"]},
        "tools": out,
        "resources": [],
        "prompts": [],
    }


def main() -> None:
    card = asyncio.run(build_card())
    CARD_PATH.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {CARD_PATH} ({len(card['tools'])} tools, all gates passed)")


if __name__ == "__main__":
    main()
