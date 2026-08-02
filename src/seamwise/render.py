"""Render canonical Markdown artifacts and Task-Spec drafts."""

from __future__ import annotations

import json
import re
from pathlib import Path
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


def _task_pack_template(task_pack_root: Path) -> str:
    path = task_pack_root / "templates" / "task-spec.md.tpl"
    if not path.is_file():
        raise FileNotFoundError(f"Task Pack template unavailable: {path}")
    return path.read_text(encoding="utf-8")


def _multiline_bash(value: str) -> str:
    return "\n  ".join(line.rstrip() for line in value.strip().splitlines())


def _markdown_inline(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_task_spec(
    *,
    task: dict[str, Any],
    intent_id: str,
    seam_id: str,
    lane_id: str,
    leg_id: str,
    source_sha256: str,
    task_pack_root: Path,
) -> str:
    """Fill the byte-preserved Task Pack template without changing its behavior."""

    template = _task_pack_template(task_pack_root).replace(
        "\n# {{TITLE}}\n", "\n# {{TITLE_HEADING}}\n", 1
    )
    if not task["touches_paths"]:
        template = template.replace(
            "touches_paths:\n{{TOUCHES_PATHS_YAML}}", "touches_paths: []", 1
        )
    behaviors = task["behavior"]
    evals = task["evals"]
    anti = task["anti_patterns"]
    touches_yaml = "\n".join(f"  - {json.dumps(path)}" for path in task["touches_paths"])
    creates_yaml = "\n".join(f"  - {json.dumps(path)}" for path in task["creates_paths"])
    do_not_touch = "\n".join(f"- `{path}`" for path in task["do_not_touch"])
    date = task["id"].split("-", 2)[1]
    created = f"{date[:4]}-{date[4:6]}-{date[6:]}T00:00:00Z"
    observability = task.get("observability", "Task-Spec eval pass count")
    replacements: dict[str, str] = {
        "ID": task["id"],
        "TITLE": json.dumps(task["title"], ensure_ascii=False),
        "TITLE_HEADING": _markdown_inline(task["title"]),
        "STATUS": "ready",
        "PROFILE": task["profile"],
        "EFFORT": task["effort"],
        "BUDGET_ITERATIONS": "15",
        "AGENT": "any",
        "DEPENDS_ON": "[" + ", ".join(task["depends_on"]) + "]",
        "TOUCHES_PATHS_YAML": touches_yaml,
        "SOURCE_NOTE": json.dumps(f"seamwise/legs/{leg_id}.md", ensure_ascii=False),
        "CREATED": created,
        "TAGS": json.dumps(["seamwise", seam_id.lower(), leg_id.lower()]),
        "TODO_PRIORITY": "P2",
        "TODO_SEVERITY": "feature",
        "TODO_DUE_DATE": "(none)",
        "WHY_ONE_PARAGRAPH": task["goal"],
        "GOAL_ONE_PARAGRAPH": task["done_condition"],
        "CONTEXT_LEAN_MAX_100_LINES": (
            f"Derived from Delivery Intent `{intent_id}` through seam `{seam_id}`, "
            f"owning swimlane `{lane_id}`, and capability leg `{leg_id}`. "
            f"Source artifact SHA-256: `{source_sha256}`."
        ),
        "B1_GIVEN": behaviors[0]["given"],
        "B1_WHEN": behaviors[0]["when"],
        "B1_THEN": behaviors[0]["then"],
        "B2_GIVEN": behaviors[1]["given"],
        "B2_WHEN": behaviors[1]["when"],
        "B2_THEN": behaviors[1]["then"],
        "EVAL_1_DESCRIPTION": json.dumps(evals[0]["description"], ensure_ascii=False),
        "EVAL_1_BASH": _multiline_bash(evals[0]["bash"]),
        "EVAL_1_DURATION": "5",
        "EVAL_2_DESCRIPTION": json.dumps(evals[1]["description"], ensure_ascii=False),
        "EVAL_2_BASH": _multiline_bash(evals[1]["bash"]),
        "EVAL_2_DURATION": "5",
        "EVAL_3_DESCRIPTION": json.dumps(evals[2]["description"], ensure_ascii=False),
        "EVAL_3_BASH": _multiline_bash(evals[2]["bash"]),
        "EVAL_3_DURATION": "10",
        "ROLLBACK_SPECIFIC_STEPS": task.get(
            "rollback", "Revert only the files listed in `touches_paths`."
        ),
        "OBSERVABILITY_EXPECTED_DURATION": "under 30 minutes",
        "OBSERVABILITY_KEY_METRIC": observability,
        "OBSERVABILITY_ALERT_CONDITION": "any deterministic eval fails",
        "OBSERVABILITY_LOG_TAIL": "(none — local deterministic task)",
        "ANTI_1_ACTION": anti[0]["action"],
        "ANTI_1_REASON": anti[0]["reason"],
        "ANTI_1_INSTEAD": anti[0]["instead"],
        "ANTI_2_ACTION": anti[1]["action"],
        "ANTI_2_REASON": anti[1]["reason"],
        "ANTI_2_INSTEAD": anti[1]["instead"],
        "ANTI_3_ACTION": anti[2]["action"],
        "ANTI_3_REASON": anti[2]["reason"],
        "ANTI_3_INSTEAD": anti[2]["instead"],
        "DO_NOT_TOUCH_LIST": do_not_touch,
        "QUESTION_1": "No open question",
        "QUESTION_1_CONTEXT": "The authored recipe is explicit and review-gated.",
        "QUESTION_2": "No inferred authority",
        "QUESTION_2_CONTEXT": "Execution and sealing remain separate explicit actions.",
    }
    placeholder_pattern = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
    template_keys = set(placeholder_pattern.findall(template))
    missing_replacements = sorted(template_keys - set(replacements))
    if missing_replacements:
        raise ValueError(
            "unfilled Task Pack placeholders: "
            + ", ".join(f"{{{{{key}}}}}" for key in missing_replacements)
        )
    text = placeholder_pattern.sub(lambda match: replacements[match.group(1)], template)
    validation_card_index = text.index("## Validation Card")
    for evaluation in evals:
        marker = f"  - id: {evaluation['id']}\n"
        marker_index = text.index(marker, validation_card_index)
        verifies_index = text.index("    verifies: ", marker_index)
        verifies_end = text.index("\n", verifies_index)
        verifies = ", ".join(evaluation["verifies"])
        text = text[:verifies_index] + f"    verifies: [{verifies}]" + text[verifies_end:]
    lineage = (
        f"delivery_intent: {intent_id}\n"
        f"seam: {seam_id}\n"
        f"swimlane: {lane_id}\n"
        f"capability_leg: {leg_id}\n"
        f"source_sha256: {source_sha256}\n"
    )
    text = text.replace("source_note:", lineage + "source_note:", 1)
    text = text.replace(
        "execution_backend: any",
        f"execution_backend: {task['execution_backend']}",
        1,
    )
    required_tools = ", ".join(task["required_tools"])
    text = text.replace(
        "required_tools: [git, bash]",
        f"required_tools: [{required_tools}]",
        1,
    )
    creates_block = f"creates_paths:\n{creates_yaml}" if creates_yaml else "creates_paths: []"
    text = text.replace("source_note:", f"{creates_block}\nsource_note:", 1)
    return text
