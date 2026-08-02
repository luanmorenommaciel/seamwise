# Lanes — three speeds, one method

## Why lanes exist

Nine gated passes on a one-line typo fix is how a method gets abandoned. METR's
randomized trial measured experienced developers **19% slower** with AI tooling
while they *believed* they were 24% faster — ceremony that does not pay for
itself is not neutral, it is negative.

A method people route around is worse than one that admits some work is small.
Lanes are that admission, made explicit and bounded.

## The three lanes

| | **FAST** | **NORMAL** | **FULL** |
|---|---|---|---|
| **passes** | 5 → 7 → 8 | 1 → 2 → 5 → 7 → 8 | 0 → 8 |
| **for** | typo, rename, one-file fix, add a test | most feature work | new system, new seam, backbone |
| **skips** | intent + structure (the change is obvious and reversible) | capture, decompose, consensus | nothing |
| **tier-2 verify** | optional | required if sensitive | required |

Every lane still ends at the **same gate**: a green eval plus the path guard.
That is what makes this one method at three speeds rather than three methods.

## Routing

```bash
cvg lane "fix a typo in the readme"
# lane      FAST
# passes    5 Tasking → 7 Bind → 8 Loop
# because   small, reversible change: readme, typo
# LANE=FAST

cvg lane "add oauth token refresh to the payment service"
# lane      NORMAL
# because   hard floor forbids FAST
# FLOOR     touches sensitive surface: auth, oauth, payment, token  (cannot be lowered)
# verify    tier-2 independent verification is REQUIRED for this work
# LANE=NORMAL
```

Deterministic and offline — keyword and shape heuristics, no model call. The same
input always produces the same lane, which means the routing itself can be
reviewed and argued with.

## The guardrail: it routes, it never waives

A classifier that can be *talked into* the fast lane makes the fast lane the only
lane, and every gate becomes theatre. So the floors are not advisory:

| Floor | Effect |
|---|---|
| touches auth · money · migrations · secrets · public API | **never FAST** |
| irreversible (delete, drop, purge, rotate, production) | **never FAST** |
| new service · new seam · greenfield · architecture | **forces FULL** |
| more than 5 files | tightens FAST → NORMAL |
| more than 15 files | tightens NORMAL → FULL |
| **no signed eval** | **dispatches in no lane at all** |

Note the asymmetry: file counts and floors only ever *tighten* the lane. Nothing
in the classifier can loosen one. And phrasing cannot defeat a floor — *"tiny
one-line typo fix in the auth token handler"* still reports the auth floor and
refuses FAST.

## What a lane does not do

- It does not waive the eval. No lane dispatches an unsigned spec.
- It does not waive the path guard. Every lane runs the postflight diff check.
- It does not decide sign-off. A human still signs at Pass 4 when Pass 4 runs.
- It does not lock you in. Blast radius discovered mid-flight **escalates** the
  lane; it never de-escalates.

## Choosing by hand

The classifier is a recommendation with floors, not an authority. If you disagree,
run the fuller lane — that direction is always allowed. The only direction that is
constrained is *downward*, and that constraint is the point.
