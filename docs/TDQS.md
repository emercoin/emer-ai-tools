# MCP tool quality — TDQS run (emercoin-agent)

Records a **TDQS** (Tool Definition Quality Score) pass over the `emercoin-agent`
MCP server (the edge's identity + memory tools). TDQS grades how well each tool
*definition* tells an agent what the tool does and when to use it — it drives
tool-selection quality, not runtime behaviour.

> Spec: <https://github.com/glama-ai/tool-definition-quality-score> (the repo
> publishes the **methodology**, not a runnable CLI). The pipeline is
> `context signals → hard gates → LLM rubric → aggregation`. We reproduce it
> locally against the live `tools/list` output: the deterministic parts (weights,
> tiers, context signals, hard gates) by `scripts/gen_server_card.py` and the
> snippet in §5, the per-dimension rubric grades by the published anchors (§2,
> justified per tool in §4). Treat absolute numbers as ±0.1–0.3 vs the official
> Glama scorer; the tier outcome (all A) is robust. Once listed, compare against
> the official score at `glama.ai/mcp`.

Last run: **2026-06-15**, against `edge/app/mcp_app.py` (5 tools).

## 1. Result

All five tools score tier **A** (passing bar is **B ≥ 3.0**); server average
**4.82 / 5** after the fixes in §3. No smells (dimension < 3), no hard-gate flags.

| Tool | TDQS | Tier | Smells |
|------|------|------|--------|
| `register_identity` | 5.0 | A | — |
| `store_memory` | 5.0 | A | — |
| `read_record` | 4.8 | A | — |
| `node_status` | 4.65 | A | — |
| `whoami` | 4.65 | A | — |
| **server avg** | **4.82** | — | — |

Baseline (before §3) was avg **4.58** — already all-A. The systematic weaknesses
were *Usage Guidelines* (read tools didn't name their sibling tools) and one
*Behavioral Transparency* gap: `register_identity` is rate-limited at runtime but
the description didn't say so.

## 2. Rubric (six dimensions, weighted)

| Dimension | Weight | What earns a 5 |
|-----------|:------:|----------------|
| Purpose Clarity | 25% | specific verb + resource; distinguishes the tool from siblings |
| Usage Guidelines | 20% | explicit when / when-not + named alternative tools |
| Behavioral Transparency | 20% | discloses side effects / prerequisites / constraints beyond annotations (1 if it **contradicts** annotations) |
| Parameter Semantics | 15% | adds meaning beyond the schema; baseline 4 for zero-param, 3 if schema description coverage > 80% |
| Conciseness & Structure | 10% | front-loaded, every sentence earns its place, no noise |
| Contextual Completeness | 10% | complete for the tool's complexity; an output schema removes the return-value burden |

`TDQS = Σ(score × weight)`, score scale 1–5. **Tiers:** A ≥ 3.5 · B ≥ 3.0 (passing)
· C ≥ 2.0 · D ≥ 1.0 · F < 1.0. **Hard gates:** empty/whitespace description →
all 1s (`No Description`); description equal to the name/title → all 1s
(`Tautological Description`); description contradicting annotations → Behavioral
Transparency = 1 (`Annotation Contradiction`). Our tools trip none.

## 3. Design choices that score well (and the fixes applied)

What was already in place and why it scores:

- **Verb-first descriptions** ("Report…", "Read…", "Create or rotate…", "Anchor…")
  so Purpose Clarity is 5 without renaming the tools. We deliberately keep the
  idiomatic names `node_status` / `whoami` rather than forcing `get_*` — the server
  is deployed and listed, and renames would break existing clients, the
  `emercoin-identity` skill and the site docs for no scoring gain.
- **A `title` per tool**, longer than and distinct from the name.
- **Behavior annotations** so descriptions needn't restate them and can't contradict
  them: `readOnlyHint` / `idempotentHint` on reads, `destructiveHint=false` +
  `idempotentHint` on `register_identity`, `openWorldHint` wherever the tool reaches
  the chain/adapter.
- **TypedDict return types** (`NodeStatus`, `NvsRecord`, `WhoAmI`, `WriteResult`)
  with `structured_output=True` so each tool emits an **output schema** → no
  return-value prose needed (Contextual Completeness).
- **Full parameter descriptions** with formats (NVS name shapes, address forms,
  content-hash semantics) → 100% schema description coverage on every parametered
  tool.
- **Clean descriptions for free:** the edge runtime pins `mcp>=1.12` (1.27.2 in
  prod), whose FastMCP runs docstrings through `cleandoc`, so no indentation leaks
  into the published descriptions (Conciseness & Structure stays at 5).

Fixes made during this run:

1. **Disclose the FREE-tier write limit on `register_identity`.** It calls
   `ratelimiter.check_and_incr` just like `store_memory`, but only `store_memory`
   said so. Added "counts against the FREE-tier per-minute write limit" → removes a
   *Behavioral Transparency* gap and the inconsistency between the two write tools.
   → 4 → 5.
2. **Name sibling tools / when-to-use across the read tools.** `read_record` now
   says it reads identity/memory records written by `register_identity` /
   `store_memory` and points at `whoami` for your github_id; `whoami` and
   `node_status` point forward at the write tools. → *Usage Guidelines* 3–4 → 5.
3. **Regenerate the static server-card from the live, clean output.**
   `site/.well-known/mcp/server-card.json` (what the Glama prober reads instead of
   opening a session) had been generated with an older SDK and carried `\n    `
   indent leaks in every description — i.e. the *card* a grader sees was noisier
   than what the live server serves. The new `scripts/gen_server_card.py` regenerates
   it from `mcp.list_tools()` under `mcp>=1.12` and asserts the hard gates, so the
   card and the running server can't drift again.

## 4. Per-dimension justifications

Grades are post-fix (§3). Each line is `dimension — score: rationale`.

### `register_identity` — 5.0 (A)

- **Purpose Clarity — 5:** Verb+resource ("Create or rotate your on-chain identity
  record `ai:gh:<github_id>`, binding an Emercoin address to your GitHub identity"),
  unambiguously the identity-write tool against its siblings.
- **Usage Guidelines — 5:** Names the flow — `whoami` first, `store_memory` after —
  and states the OAuth precondition.
- **Behavioral Transparency — 5:** Post-fix it discloses everything annotations
  can't carry: signed-in required, the FREE-tier rate limit, gateway-paid (no EMC),
  pending→confirmed timing, and that it is idempotent (rebinds on re-call), matching
  `idempotentHint`.
- **Parameter Semantics — 5:** 100% coverage; `address` carries the key-control /
  signature-login anchor semantics, `metadata` its verbatim-storage contract.
- **Conciseness & Structure — 5:** Front-loaded on the action; every clause is a
  distinct precondition, cost or guarantee.
- **Contextual Completeness — 5:** Output schema present; the description covers the
  full lifecycle and follow-ups.

### `store_memory` — 5.0 (A)

- **Purpose Clarity — 5:** Verb+resource ("Anchor a memory/artifact on-chain as the
  NVS record `ai:gh:<github_id>:mem:<content_hash>`"), distinct from the identity
  write.
- **Usage Guidelines — 5:** "Register your identity first" names the prerequisite
  sibling; when-to-use is explicit.
- **Behavioral Transparency — 5:** Discloses the rate limit, gateway-paid writes,
  pending→confirmed timing, and **not** idempotent (each hash is a new record),
  consistent with `idempotentHint=false`.
- **Parameter Semantics — 5:** 100% coverage; `content_hash` explains the off-chain
  body / on-chain fingerprint split, `metadata` its contract.
- **Conciseness & Structure — 5:** Tight, front-loaded, no filler.
- **Contextual Completeness — 5:** Output schema present; lifecycle fully covered.

### `read_record` — 4.8 (A)

- **Purpose Clarity — 5:** Verb+resource ("Read one Emercoin NVS record by its full
  name"), naming the two record shapes; clearly the read-by-name tool.
- **Usage Guidelines — 5:** Post-fix it names the writers (`register_identity` /
  `store_memory`) whose records it reads and points at `whoami` to obtain your
  github_id.
- **Behavioral Transparency — 4:** Read-only is in annotations; the prose adds the
  confirmed-vs-pending distinction and null-for-missing behaviour. No side effects
  or prerequisites to disclose.
- **Parameter Semantics — 5:** Single `name` param at 100% coverage, documenting both
  NVS name formats with examples.
- **Conciseness & Structure — 5:** Front-loaded, no indentation noise.
- **Contextual Completeness — 5:** Output schema present and the `status` field is
  summarised; complete for a read.

### `node_status` — 4.65 (A)

- **Purpose Clarity — 5:** Verb+resource ("Report the Emercoin node's version, block
  height, header height, peer connections and sync state"), distinct from the
  record tools.
- **Usage Guidelines — 5:** Post-fix it says when ("first in a session") and names
  the siblings it gates (`read_record`, `register_identity`, `store_memory`).
- **Behavioral Transparency — 4:** Read-only/idempotent in annotations; the prose
  adds the `synced` semantics (block == header). No side effects to disclose.
- **Parameter Semantics — 4:** Zero-parameter tool → baseline 4; nothing to document.
- **Conciseness & Structure — 5:** Compact, front-loaded, no noise.
- **Contextual Completeness — 5:** Output schema present; the status fields are still
  summarised.

### `whoami` — 4.65 (A)

- **Purpose Clarity — 5:** Verb+resource ("Report the current session's identity"),
  distinct from `read_record`.
- **Usage Guidelines — 5:** Post-fix it names `register_identity` / `store_memory` as
  the writes it precedes and states the sign-in when-not for anonymous callers.
- **Behavioral Transparency — 4:** Read-only in annotations; the prose adds the
  non-obvious anonymous-vs-signed-in payloads and that anonymous is **not** an error.
- **Parameter Semantics — 4:** Zero-parameter tool → baseline 4.
- **Conciseness & Structure — 5:** Three compact sentences, front-loaded.
- **Contextual Completeness — 5:** Output schema present; both payload shapes are
  described.

## 5. How to re-run

Regenerate the card and re-check the deterministic gates (indent leak, output
schema, tautology) in one step — run from the repo root in a venv with
`edge/requirements.txt` installed:

```bash
EDGE_DEV_LOGIN_ENABLED=true PYTHONPATH=. python scripts/gen_server_card.py
```

Dump the live definitions + context signals to grade by hand against §2:

```bash
EDGE_DEV_LOGIN_ENABLED=true PYTHONPATH=. python - <<'PY'
import asyncio, json
from edge.app import mcp_app

async def main():
    rows = []
    for t in await mcp_app.mcp.list_tools():
        props = (t.inputSchema or {}).get("properties", {})
        described = [k for k, v in props.items() if isinstance(v, dict) and v.get("description")]
        rows.append({
            "name": t.name,
            "title": t.title,
            "annotations": t.annotations and t.annotations.model_dump(exclude_none=True),
            "schemaDescriptionCoverage": (len(described) / len(props)) if props else None,
            "hasOutputSchema": bool(t.outputSchema),
            "indentLeak": "\n    " in (t.description or ""),         # should be False
            "tautologyGate": (t.description or "").strip().lower()
                              in {t.name.lower(), (t.title or "").lower()},
        })
    print(json.dumps(rows, indent=2, ensure_ascii=False))

asyncio.run(main())
PY
```

Then grade each tool on the §2 anchors and aggregate:

```bash
python - <<'PY'
W = dict(purpose_clarity=.25, usage_guidelines=.20, behavioral_transparency=.20,
         parameter_semantics=.15, conciseness_structure=.10, contextual_completeness=.10)
tier = lambda x: "A" if x >= 3.5 else "B" if x >= 3.0 else "C" if x >= 2.0 else "D" if x >= 1.0 else "F"
tdqs = lambda s: round(sum(s[k] * W[k] for k in W), 2)

# fill from the §4 grading (1–5 per dimension)
scores = {
    "node_status":       dict(purpose_clarity=5, usage_guidelines=5, behavioral_transparency=4,
                              parameter_semantics=4, conciseness_structure=5, contextual_completeness=5),
    "read_record":       dict(purpose_clarity=5, usage_guidelines=5, behavioral_transparency=4,
                              parameter_semantics=5, conciseness_structure=5, contextual_completeness=5),
    "whoami":            dict(purpose_clarity=5, usage_guidelines=5, behavioral_transparency=4,
                              parameter_semantics=4, conciseness_structure=5, contextual_completeness=5),
    "register_identity": dict(purpose_clarity=5, usage_guidelines=5, behavioral_transparency=5,
                              parameter_semantics=5, conciseness_structure=5, contextual_completeness=5),
    "store_memory":      dict(purpose_clarity=5, usage_guidelines=5, behavioral_transparency=5,
                              parameter_semantics=5, conciseness_structure=5, contextual_completeness=5),
}
tot = 0
for name, s in scores.items():
    v = tdqs(s); tot += v
    print(f"{name:18} TDQS {v}  tier {tier(v)}  smells={[k for k, x in s.items() if x < 3] or '—'}")
print(f"{'server avg':18} {round(tot / len(scores), 2)}")
PY
```
