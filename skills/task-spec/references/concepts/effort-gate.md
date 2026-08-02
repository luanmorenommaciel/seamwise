# Effort Gate

> **Purpose**: XS/S/M/L/XL/XXL classification — the size-based safety primitive that
> keeps every unit right-sized and keeps the pipeline on ONE path: tasking.
> **Confidence**: HIGH
> **MCP Validated**: 2026-05-19 · six-tier + fork-collapse (v3.4) 2026-07-21
> (research: Young, Anthropic context-engineering, Vaughan/Codex-KB, Vest — 2026)

## The one path (v3.4 — tasks all the way down)

Converge no longer forks between a plan-driven spec (Fork A / SDD) and a task-driven
decomposition (Fork B). **There is one path: everything becomes a Task-Spec, at every
scale.** Big work is not routed *out* to a different paradigm — it is *decomposed* into
smaller Task-Specs, recursively, until every leaf is a runnable atom. The reason is
empirical: frontier models (GPT‑5, Opus/Fable, Kimi K2) execute well-scoped atoms
reliably, and a tree of verified atoms composes back up more safely than one giant
spec. The gate is what keeps the atoms atomic.

## Two KINDS of size

```text
LEAVES  (runnable atoms — fit ONE fresh context window, verify as ONE PR/test-suite)
  XS → Task-Spec ✅  → recommend Kimi   (sprinter: fast atomic crank)
  S  → Task-Spec ✅  → recommend Kimi
  M  → Task-Spec ✅  → recommend Kimi
  L  → Task-Spec ✅* → recommend GLM    (marathoner: long-horizon builder)
       *ACCEPTED ONLY on a LONG-HORIZON builder AND ONE coherent done-condition.
        If it needs multiple independent evals → decompose.

NODES   (decomposition directives — NOT runnable; they expand into leaves)
  XL  → Task-Spec ⇗  → MUST declare children: (>= 2 child task-spec ids)
  XXL → Task-Spec ⇗  → MUST declare children: (>= 3 child task-spec ids)
       A node owns NO write surface — its children do. A worker dispatches the
       children (leaves) and composes their results back up. There is no route out.
```

## Size by context + verification + blast-radius (NOT by human time)

The real limiter for an agent is not lines of code or wall-clock — it is **how much
context it must consume to act safely** and **whether the result verifies
independently**. The gate enforces the one objective, machine-checkable proxy it can
see in the spec: the **write surface** (`|touches_paths ∪ creates_paths|`). A leaf that
declares more write paths than its tier allows is mis-sized — split it or reclassify UP.
Budgets are not arbitrary; a breach is decomposition feedback (Vest, 2026).

| Class | Kind | Write-surface budget | Reads (guide) | Evals | Backend | Example |
|-------|------|----------------------|---------------|-------|---------|---------|
| **XS** | leaf | ≤ 1 path | ≤ 2 files | 1 | Kimi | bump a dep; fix a constant; add one config key |
| **S**  | leaf | ≤ 2 paths | ≤ 4 files | 1–2 | Kimi | add a `/health` endpoint; one small model |
| **M**  | leaf | ≤ 3 paths | ≤ 6 files | 2–3 | Kimi | a new endpoint family; a dbt model + its test |
| **L**  | leaf (ceiling) | ≤ 5 paths | ≤ 10 files | ≤ 4, ONE goal | **long-horizon** (glm/claude/codex/kimi) | migrate one service end-to-end as one coherent goal |
| **XL** | **node** | 0 (decomposes) | — | children's | *expands* | a whole swimlane; a feature spanning ≥2 layers |
| **XXL**| **node** | 0 (decomposes) | — | children's | *expands* | a backbone; a platform slice → epic → slices → atoms |

Reads/evals columns are authoring guidance (files-to-read ~5–6 is the split trigger,
~10 the ceiling — Crosley/Young; a single test-suite keeps, multiple independent split
— Vaughan). Only the **write-surface budget** is gate-enforced today; the rest is the
classifier's job.

## Why the gate matters

| Property | XS/S/M (Kimi) | L (GLM, one goal) | XL/XXL (node) |
|----------|---------------|-------------------|---------------|
| Fits one fresh context window | Yes | Usually | No — that's why it decomposes |
| Single PR fits | Yes | Usually | No (its children each do) |
| Verified independently | One suite | One coherent done-condition | Each child, then composed |
| Autonomous overnight run | Sane | Sane on GLM | Only the leaves run |
| Recovery if it fails | Park, retry | Park, resume GLM | Re-slice the node |

## The classifier (task-architect agent)

```text
SIGNAL                                      → IMPLIES
─────────────────────────────────────────────────────
Trivial one-liner / config tweak            → XS
1 file changes                              → S
2-3 closely-related files                   → S or M
Multiple modules, one coherent goal         → M (or L on a long-horizon builder)
New top-level dir / cross-language, one goal → L (→ GLM)
Crosses >= 2 architectural layers            → XL (decompose along layer seams)
A whole swimlane / feature / backbone        → XL or XXL (decompose)
"big" / "platform" / multi-team in intent    → XXL (decompose into an epic tree)
```

**XS/S/M** → accept, recommend Kimi. **L** → accept ONLY on a long-horizon builder (`TS_LONG_HORIZON_BACKENDS`, default: glm claude codex kimi)
and ONE coherent done-condition (else decompose). **XL/XXL** → accept ONLY with a
`children:` block; otherwise the gate refuses — not to route out, but to force the
decomposition. When the classifier returns XL/XXL, the agent outputs:

```text
This is XL/XXL effort — a decomposition NODE, not a runnable Task-Spec.

Expand it into child Task-Specs (the vertical slices), each a runnable leaf (XS–L):
  parent:   T-<date>-<this-node>
  children: [T-…-slice-1, T-…-slice-2, …]   (>= 2 for XL, >= 3 for XXL)

Split along the natural seams (architectural layers, swimlane legs, independent
test-suites). Then dispatch the leaves; the node composes their results back up.
```

## Edge cases

### "It's actually two tasks"
If a task feels L because it's two M tasks bundled — DECOMPOSE. If it feels XL, it *is*
a node: give it `children:` and slice along the seams.

```text
Original (XL, node): "Migrate auth from JWT to OAuth2 across all services"
  parent:   T-…-auth-oauth2-migration        (XL, children below)
  children:
    T-1 (M): add OAuth2 provider in auth-service
    T-2 (M): switch user-service to OAuth2 client
    T-3 (M): switch admin-service to OAuth2 client
    T-4 (S): remove JWT code paths after migration verified
```

### "It LOOKS small but actually isn't"
Some 1-file changes are L in disguise — a critical, fragile module. RED FLAGS: file
> 500 lines with high coverage; many CODEOWNERS; lives in `src/core|auth|billing/`; the
last 5 commits all needed follow-up fixes. When in doubt, classify UP.

### "I want to force a node to run as a leaf"
Don't. The gate refuses an XL/XXL without `children:` — bypassing it is how you get a
half-baked spec for work that needed slicing. Decompose; the leaves are where the work
actually runs.

## Related
- [task-spec-v1.md](task-spec-v1.md) — frontmatter spec for `effort` + `children`
- [profiles.md](profiles.md) — effort-scaled profiles (lite/standard/full)
- [agent-contract.md](agent-contract.md) — how the agent refuses / decomposes
