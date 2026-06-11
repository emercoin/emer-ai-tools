"""NVS naming policy — the `ai:gh:<id>` namespace lives here, in the edge.

The adapter is policy-free; it's the edge that decides how an agent's identity and
memory records are named, so agents can't collide or overwrite each other:
  ai:gh:<github_id>            -> root identity record
  ai:gh:<github_id>:mem:<hash> -> a research/memory pointer
"""
from __future__ import annotations

import json
from typing import Any


def root_name(github_id: int) -> str:
    return f"ai:gh:{github_id}"


def mem_name(github_id: int, content_hash: str) -> str:
    return f"ai:gh:{github_id}:mem:{content_hash}"


def parse_identity(record: dict[str, Any]) -> dict[str, Any]:
    """Parse the JSON value of an on-chain identity record; {} if not valid JSON."""
    try:
        return json.loads(record.get("value", "{}"))
    except (ValueError, TypeError):
        return {}
