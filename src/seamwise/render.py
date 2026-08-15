"""Render canonical Seamwise-owned Markdown artifacts."""

from __future__ import annotations

from typing import Any

from seamwise.io import dump_frontmatter


def render_intent(intent: dict[str, Any]) -> str:
    frontmatter = {
        "schema_version": 1,
        "kind": "delivery-intent",
        "id": intent["id"],
        "title": intent["title"],
        "claim": intent["claim"],
        "source": intent["source"],
        "success": intent["success"],
        "out_of_scope": intent["out_of_scope"],
    }
    body = f"""# {intent["title"]}

## Delivery outcome

{intent["summary"]}

## Evidence boundary

This artifact records a **{intent["claim"]}** claim. Its source, capture time,
and content hash are recorded in frontmatter; the claim is not implementation
evidence by itself.
"""
    return dump_frontmatter(frontmatter, body)


def render_system_map(system_map: dict[str, Any], recipe: dict[str, Any]) -> str:
    frontmatter = {
        "schema_version": 1,
        "kind": "system-map",
        "claim": system_map["claim"],
        "components": system_map["components"],
        "external_dependencies": system_map["external_dependencies"],
        "unknowns": system_map["unknowns"],
        "proposed_steel_thread": recipe["steel_thread"],
        "objections": recipe.get("objections", []),
        "contentions": recipe.get("contentions", []),
    }
    components = "\n".join(f"- {item}" for item in system_map["components"])
    dependencies = (
        "\n".join(f"- {item}" for item in system_map["external_dependencies"])
        or "- (none recorded)"
    )
    unknowns = "\n".join(f"- {item}" for item in system_map["unknowns"]) or "- (none)"
    body = f"""# System Map

## Components

{components}

## External dependencies

{dependencies}

## Unknowns

{unknowns}

This is a **{system_map["claim"]}** map. The delivery-plan transformation must
close or gate every material unknown; it may not reinterpret this text as
runtime proof.
"""
    return dump_frontmatter(frontmatter, body)


def render_decision(decision: dict[str, Any]) -> str:
    frontmatter = {"schema_version": 1, "kind": "decision", **decision}
    body = f"""# {decision["id"]}

Status: **{decision["status"]}**

Owner: {decision["owner"]}

## Rationale

{decision["rationale"]}
"""
    return dump_frontmatter(frontmatter, body)


def render_seam(seam: dict[str, Any]) -> str:
    frontmatter = {
        "schema_version": 1,
        "kind": "seam",
        "claim": "derived",
        **seam,
    }
    rejected = "\n".join(
        f"- **{item['alternative']}** — {item['reason']}" for item in seam["rejected_alternatives"]
    )
    body = f"""# {seam["name"]}

{seam["description"]}

## Responsibility

{seam["responsibility"]}

## Independent proof

{seam["independent_proof"]}

## Rejected alternatives

{rejected}

This derived seam is ready only while its cited evidence, named owner, contract,
and rejected alternatives remain intact.
"""
    return dump_frontmatter(frontmatter, body)


def render_swimlane(lane: dict[str, Any], seam_id: str, source_sha256: str) -> str:
    frontmatter = {
        "schema_version": 1,
        "kind": "swimlane",
        "claim": "derived",
        "id": lane["id"],
        "name": lane["name"],
        "owner": lane["owner"],
        "seam_id": seam_id,
        "source_seam_sha256": source_sha256,
        "legs": [item["id"] for item in lane["legs"]],
    }
    body = f"""# {lane["name"]}

This is the single owning swimlane for `{seam_id}`. Ownership is `{lane["owner"]}`.
Sibling capability legs are ordered only by explicit dependencies or recorded
contention—not by their position in this file.
"""
    return dump_frontmatter(frontmatter, body)


def render_leg(leg: dict[str, Any], seam_id: str, lane_id: str, source_sha256: str) -> str:
    frontmatter = {
        "schema_version": 1,
        "kind": "capability-leg",
        "claim": "derived",
        "id": leg["id"],
        "seam_id": seam_id,
        "swimlane_id": lane_id,
        "observable_state": leg["observable_state"],
        "proof": leg["proof"],
        "requires": leg["requires"],
        "produces": leg["produces"],
        "tasks": leg["tasks"],
        "source_seam_sha256": source_sha256,
    }
    task_list = "\n".join(
        f"- `{task['id']}` — {task['title']}: {task['done_condition']}" for task in leg["tasks"]
    )
    body = f"""# {leg["observable_state"]}

## Observable proof

{leg["proof"]}

## Runnable leaves

{task_list}

The leg names a capability state, not an activity. Each leaf owns one coherent,
independently provable done-condition.
"""
    return dump_frontmatter(frontmatter, body)


def render_steel_thread(leg_ids: list[str], legs: list[dict[str, Any]]) -> str:
    by_id = {item["id"]: item for item in legs}
    ordered = [by_id[leg_id] for leg_id in leg_ids]
    lines = ["# Steel Thread", ""]
    for index, leg in enumerate(ordered, start=1):
        lines.append(f"{index}. [`{leg['id']}`](legs/{leg['id']}.md)")
    lines.extend(
        [
            "",
            "This is a derived critical capability path. It records ordering, not",
            "implementation completion or dispatch authority.",
            "",
        ]
    )
    return "\n".join(lines)
