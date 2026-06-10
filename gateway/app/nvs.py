"""NVS domain — agent identity + memory/research records on the Emercoin chain.

Names are namespaced per GitHub identity so agents can't collide or overwrite
each other:
  ai:gh:<github_id>            -> root identity record
  ai:gh:<github_id>:mem:<hash> -> a research/memory pointer

On-chain the records are owned by the gateway hot-wallet; agent ownership is
asserted inside the value (github_id + pubkey [+ signature]).
"""
from __future__ import annotations

import json
from typing import Any

from .rpc import EmercoinRPC


def root_name(github_id: int) -> str:
    return f"ai:gh:{github_id}"


def mem_name(github_id: int, content_hash: str) -> str:
    return f"ai:gh:{github_id}:mem:{content_hash}"


async def write_record(rpc: EmercoinRPC, name: str, value: dict[str, Any], days: int) -> Any:
    """Register/update an NVS name. Emercoin name_new is single-step (name value days)."""
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return await rpc.call("name_new", name, encoded, days)


async def show_record(rpc: EmercoinRPC, name: str) -> dict[str, Any]:
    return await rpc.call("name_show", name)
