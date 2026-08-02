#!/usr/bin/env python3
"""Route work to the lane it earns — FAST, NORMAL or FULL.

WHY THIS EXISTS
Nine gated passes on a typo is how a method gets abandoned. METR's RCT measured
developers 19% SLOWER with AI tooling while believing they were 24% faster, so
ceremony that does not pay for itself is not neutral — it is negative. A method
people route around is worse than one that admits some work is small.

THE GUARDRAIL
This classifier ROUTES; it never WAIVES. Its floors cannot be lowered by any
argument, because a classifier that can be talked into the fast lane makes the
fast lane the only lane and turns every gate into theatre:

  * touches auth / money / migrations / secrets / public API  -> never FAST
  * irreversible or hard-to-reverse                            -> never FAST
  * a new seam, service, or system                             -> FULL
  * no signed eval                                             -> dispatches in NO lane

Every lane still ends at the same gate: a green eval plus the path guard. Three
speeds, one method.

Deterministic and offline: keyword+shape heuristics, no model call, same input
always yields the same lane. Advisory to a human, hard-floored against a machine.

Usage:  classify-lane.py "<intent>" [--files N] [--paths a,b] [--json]
Token:  LANE=FAST|NORMAL|FULL|USAGE_ERROR
"""

from __future__ import annotations

import argparse
import json
import re

# --- Hard floors: presence forces the lane, whatever the prose suggests. -----
SENSITIVE = (
    "auth", "authn", "authz", "login", "signin", "session", "oauth", "jwt",
    "token", "secret", "credential", "password", "encrypt", "crypto", "permission",
    "payment", "billing", "invoice", "charge", "refund", "price", "money",
    "migration", "schema change", "alter table", "drop table", "backfill",
    "public api", "breaking change", "rate limit", "pii", "gdpr",
)
IRREVERSIBLE = (
    "delete", "drop", "purge", "wipe", "truncate", "destroy", "rotate",
    "deploy to prod", "production", "irreversible", "one-way",
)
# --- Shape signals: what KIND of work is this? ------------------------------
GREENFIELD = (
    "new service", "new system", "from scratch", "greenfield", "architecture",
    "redesign", "rearchitect", "platform", "end-to-end", "backbone", "pipeline",
    "multiple services", "new seam",
)
FEATURE = (
    "add", "implement", "support", "introduce", "build", "create", "extend",
    "endpoint", "feature", "integrate",
)
TRIVIAL = (
    "typo", "rename", "comment", "docstring", "lint", "format", "whitespace",
    "bump", "changelog", "readme", "log message", "error message",
    "add a test", "add test", "fix test", "flaky",
)


def _hits(text: str, needles: tuple[str, ...]) -> list[str]:
    return sorted({n for n in needles if n in text})


def classify(intent: str, files: int | None, paths: list[str]) -> dict:
    text = f"{intent} {' '.join(paths)}".lower()
    text = re.sub(r"\s+", " ", text)

    sensitive = _hits(text, SENSITIVE)
    irreversible = _hits(text, IRREVERSIBLE)
    greenfield = _hits(text, GREENFIELD)
    trivial = _hits(text, TRIVIAL)
    feature = _hits(text, FEATURE)

    reasons: list[str] = []
    floors: list[str] = []

    # ---- Floors first. These are not advisory. ----
    if sensitive:
        floors.append(f"touches sensitive surface: {', '.join(sensitive)}")
    if irreversible:
        floors.append(f"hard to reverse: {', '.join(irreversible)}")

    if greenfield:
        lane = "FULL"
        reasons.append(f"new system or seam signalled by: {', '.join(greenfield)}")
    elif floors:
        # Sensitive/irreversible never rides FAST; it needs the design passes
        # that make intent explicit, but not necessarily a fresh BRD.
        lane = "NORMAL"
        reasons.append("hard floor forbids FAST")
    elif trivial and not feature:
        lane = "FAST"
        reasons.append(f"small, reversible change: {', '.join(trivial)}")
    elif feature:
        lane = "NORMAL"
        reasons.append(f"new behaviour signalled by: {', '.join(feature)}")
    else:
        lane = "NORMAL"
        reasons.append("no strong signal — defaulting to NORMAL (the safe middle)")

    # File count only ever TIGHTENS.
    if files is not None:
        if files > 5 and lane == "FAST":
            lane = "NORMAL"
            reasons.append(f"{files} files exceeds the FAST ceiling of 5")
        elif files > 15 and lane == "NORMAL":
            lane = "FULL"
            reasons.append(f"{files} files is a system-shaped change")

    passes = {
        "FAST": ["5 Tasking", "7 Bind", "8 Loop"],
        "NORMAL": ["1 Intent", "2 Structure", "5 Tasking", "7 Bind", "8 Loop"],
        "FULL": ["0 Capture", "1 Intent", "2 Structure", "3 Decompose",
                 "4 Consensus", "5 Tasking", "6 Register", "7 Bind", "8 Loop"],
    }[lane]

    return {
        "schema": "cvg.lane.v1",
        "lane": lane,
        "passes": passes,
        "reasons": reasons,
        "hard_floors": floors,
        "verification_required": bool(floors) or lane == "FULL",
        "note": (
            "Advisory routing with hard floors. It can never waive a gate: every "
            "lane ends at a green eval plus the path guard, and no lane dispatches "
            "an unsigned spec."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Route work to FAST, NORMAL or FULL.")
    ap.add_argument("intent", nargs="*", help="what you intend to do, in a sentence")
    ap.add_argument("--files", type=int, help="how many files the change touches")
    ap.add_argument("--paths", default="", help="comma-separated paths it will touch")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    intent = " ".join(args.intent).strip()
    if not intent:
        print("FAIL: describe the intent, e.g. cvg lane \"add a health endpoint\"")
        print("LANE=USAGE_ERROR")
        return 2

    paths = [p.strip() for p in args.paths.split(",") if p.strip()]
    result = classify(intent, args.files, paths)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"lane      {result['lane']}")
        print(f"passes    {' → '.join(result['passes'])}")
        for reason in result["reasons"]:
            print(f"because   {reason}")
        for floor in result["hard_floors"]:
            print(f"FLOOR     {floor}  (cannot be lowered)")
        if result["verification_required"]:
            print("verify    tier-2 independent verification is REQUIRED for this work")
    print(f"LANE={result['lane']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
