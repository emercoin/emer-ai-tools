"""NVS (name-value storage) mechanics over the node RPC.

This layer is policy-free: it knows how to create / update / read NVS names and
nothing about who owns them. Naming conventions (e.g. the `ai:gh:<id>` namespace)
and authorization live above the adapter, in the edge service.
"""
from __future__ import annotations

import json
from typing import Any

from .rpc import EmercoinRPC, RPCError


def _encode(value: Any) -> str:
    """A value may arrive as a dict (encode it) or an already-serialized string."""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


async def name_exists(rpc: EmercoinRPC, name: str) -> bool:
    """True if the name is already registered (confirmed in the name DB or sitting
    unconfirmed in the mempool). Determines name_new vs name_update."""
    try:
        await show_record(rpc, name)
        return True
    except RPCError:
        pass
    return await find_in_mempool(rpc, name) is not None


async def write_record(rpc: EmercoinRPC, name: str, value: Any, days: int) -> Any:
    """Register or update an NVS name (both single-step: name value days).

    name_new fails on a name that already exists, so a re-registration (e.g. key
    rotation: same name, new value) must go through name_update.
    """
    method = "name_update" if await name_exists(rpc, name) else "name_new"
    return await rpc.call(method, name, _encode(value), days)


async def write_batch(rpc: EmercoinRPC, operations: list[dict[str, Any]]) -> Any:
    """Atomic multi-record write in a single transaction (name_updatemany).

    `operations` is a list of {name, value, days}; returns one txid for the whole
    batch. Note: raw JSON-RPC wants a native array here (not the string form shown
    in bitcoin-cli examples).
    """
    ops = [
        {"NEW": op["name"], "value": _encode(op["value"]), "days": op["days"]}
        for op in operations
    ]
    return await rpc.call("name_updatemany", ops)


async def show_record(rpc: EmercoinRPC, name: str) -> dict[str, Any]:
    return await rpc.call("name_show", name)


async def show_history(rpc: EmercoinRPC, name: str) -> Any:
    """Full value history of a name (name_history)."""
    return await rpc.call("name_history", name)


async def names_for_address(rpc: EmercoinRPC, address: str) -> Any:
    """All names owned by an address (name_scan_address)."""
    return await rpc.call("name_scan_address", address)


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
