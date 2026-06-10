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

from .rpc import EmercoinRPC, RPCError


def root_name(github_id: int) -> str:
    return f"ai:gh:{github_id}"


def mem_name(github_id: int, content_hash: str) -> str:
    return f"ai:gh:{github_id}:mem:{content_hash}"


async def name_exists(rpc: EmercoinRPC, name: str) -> bool:
    """True if the name is already registered (confirmed in the name DB or sitting
    unconfirmed in the mempool). Determines name_new vs name_update."""
    try:
        await show_record(rpc, name)
        return True
    except RPCError:
        pass
    return await find_in_mempool(rpc, name) is not None


async def write_record(rpc: EmercoinRPC, name: str, value: dict[str, Any], days: int) -> Any:
    """Register or update an NVS name (both single-step: name value days).

    name_new fails on a name that already exists, so a re-registration (e.g. key
    rotation: same identity name, new value) must go through name_update.
    """
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    method = "name_update" if await name_exists(rpc, name) else "name_new"
    return await rpc.call(method, name, encoded, days)


async def show_record(rpc: EmercoinRPC, name: str) -> dict[str, Any]:
    return await rpc.call("name_show", name)


async def show_history(rpc: EmercoinRPC, name: str) -> Any:
    """Full value history of a name (name_history)."""
    return await rpc.call("name_history", name)


async def names_for_address(rpc: EmercoinRPC, address: str) -> Any:
    """All names owned by an address (name_scan_address)."""
    return await rpc.call("name_scan_address", address)


def mem_operation(github_id: int, content_hash: str, metadata: dict, days: int) -> dict[str, Any]:
    """Build one name_updatemany NEW op for a memory record."""
    value = {"github_id": github_id, "content_hash": content_hash, "metadata": metadata}
    return {
        "NEW": mem_name(github_id, content_hash),
        "value": json.dumps(value, separators=(",", ":"), ensure_ascii=False),
        "days": days,
    }


async def write_batch(rpc: EmercoinRPC, operations: list[dict[str, Any]]) -> Any:
    """Atomic multi-record write in a single transaction (name_updatemany).

    Returns one txid for the whole batch. Note: raw JSON-RPC wants a native
    array here (not the string form shown in bitcoin-cli examples).
    """
    return await rpc.call("name_updatemany", operations)


async def find_in_mempool(rpc: EmercoinRPC, name: str) -> dict[str, Any] | None:
    """A just-written name lives in the mempool until a block confirms it;
    name_show can't see it yet, but name_mempool can."""
    try:
        entries = await rpc.call("name_mempool")
    except RPCError:
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


async def get_identity(rpc: EmercoinRPC, github_id: int) -> dict[str, Any]:
    """Read and parse the on-chain identity record value for a GitHub id.

    Returns {} if the name does not exist or its value is not valid JSON.
    """
    try:
        record = await show_record(rpc, root_name(github_id))
    except RPCError:
        return {}
    try:
        return json.loads(record.get("value", "{}"))
    except (ValueError, TypeError):
        return {}
