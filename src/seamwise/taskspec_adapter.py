"""Pure TaskPlan projection boundary for independently coordinated engines.

Seamwise owns reviewed decomposition and lineage. It deliberately does not
invoke, import, vendor, validate, or materialize through Task-Spec. A caller
such as Converge passes these two artifacts to the independent Task-Spec CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from seamwise.constants import VERSION
from seamwise.io import (
    canonical_json,
    load_frontmatter,
    load_json,
    sha256_bytes,
    sha256_file,
)
from seamwise.result import Diagnostic

TASK_PLAN_CONTRACT = "TaskPlan/v1"
TASK_PLAN_LINEAGE_CONTRACT = "SeamwiseTaskPlanLineage/v1"
TASK_PLAN_PATH = Path("seamwise/task-plan.json")
TASK_PLAN_LINEAGE_PATH = Path("seamwise/task-plan-lineage.json")


def _anti_pattern(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    action = str(value.get("action", "")).strip()
    reason = str(value.get("reason", "")).strip()
    instead = str(value.get("instead", "")).strip()
    return f"Do not {action}: {reason}; instead {instead}."


def build_task_plan(
    root: Path, plan: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Project reviewed Seamwise units into Task-Spec's public TaskPlan contract."""

    intent, _ = load_frontmatter(root / "seamwise" / "intent.md")
    plan_path = root / "seamwise" / "delivery-plan.yaml"
    review_path = root / "seamwise" / "reviews" / "delivery-plan-review.json"
    units: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: str(item["task"]["id"])):
        task = record["task"]
        evals = [
            {
                "id": check["id"],
                "description": check["description"],
                "command": check["bash"],
                "verifies": check["verifies"],
                "terminal": index == len(task["evals"]),
                "expected_duration_sec": 10,
            }
            for index, check in enumerate(task["evals"], 1)
        ]
        context = (
            f"Intent {intent['id']}; seam {record['seam_id']}; swimlane "
            f"{record['swimlane_id']}; capability leg {record['leg_id']}. "
            f"Done condition: {task['done_condition']}"
        )
        units.append(
            {
                "id": task["id"],
                "title": task["title"],
                "effort": task["effort"],
                "profile": task["profile"],
                "agent": "any",
                "execution_backend": task["execution_backend"],
                "required_tools": task["required_tools"],
                "depends_on": task["depends_on"],
                "touches_paths": task["touches_paths"],
                "creates_paths": task["creates_paths"],
                "source_note": f"{record['leg_path']}#{task['id']}",
                "why": task["goal"],
                "goal": task["goal"],
                "done_condition": task["done_condition"],
                "context": context,
                "do_not_touch": task["do_not_touch"],
                "anti_patterns": [_anti_pattern(item) for item in task["anti_patterns"]],
                "rollback": task["rollback"],
                "observability": task["observability"],
                "behaviors": task["behavior"],
                "evals": evals,
            }
        )
    return {
        "api_version": "taskspec.dev/v1",
        "kind": "TaskPlan",
        "approved": True,
        "metadata": {
            "name": str(intent["id"]),
            "source": str(TASK_PLAN_PATH),
            "producer": "seamwise",
            "producer_version": VERSION,
            "delivery_plan_sha256": sha256_file(plan_path),
            "delivery_plan_review_sha256": sha256_file(review_path),
            "seamwise_plan_status": plan["status"],
        },
        "units": units,
    }


def task_plan_digest(task_plan: dict[str, Any]) -> str:
    """Match Task-Spec's canonical JSON digest without importing its engine."""

    return sha256_bytes(canonical_json(task_plan).encode("utf-8"))


def build_task_plan_lineage(
    root: Path,
    records: list[dict[str, Any]],
    task_plan: dict[str, Any],
) -> dict[str, Any]:
    """Bind every emitted unit to review, intent, seam, lane, and leg evidence."""

    intent_path = root / "seamwise" / "intent.md"
    plan_path = root / "seamwise" / "delivery-plan.yaml"
    review_path = root / "seamwise" / "reviews" / "delivery-plan-review.json"
    intent, _ = load_frontmatter(intent_path)
    review = load_json(review_path)
    return {
        "contract": TASK_PLAN_LINEAGE_CONTRACT,
        "engine_version": VERSION,
        "intent": {
            "id": intent["id"],
            "sha256": sha256_file(intent_path),
        },
        "delivery_plan_sha256": sha256_file(plan_path),
        "review": {
            "sha256": sha256_file(review_path),
            "plan_sha256": review["plan_sha256"],
            "reviewer": review["reviewer"],
            "reviewed_at": review["reviewed_at"],
            "fixture": bool(review.get("fixture")),
        },
        "task_plan": {
            "contract": TASK_PLAN_CONTRACT,
            "path": TASK_PLAN_PATH.as_posix(),
            "digest": task_plan_digest(task_plan),
        },
        "units": {
            record["task"]["id"]: {
                "unit_id": record["task"]["id"],
                "intent": intent["id"],
                "seam": record["seam_id"],
                "swimlane": record["swimlane_id"],
                "leg": record["leg_id"],
                "source_sha256": record["source_sha256"],
            }
            for record in sorted(records, key=lambda item: str(item["task"]["id"]))
        },
    }


def verify_task_plan_bundle(
    root: Path,
    plan: dict[str, Any],
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[Diagnostic]]:
    """Verify only Seamwise-owned projections; Task-Spec validation stays external."""

    plan_path = root / TASK_PLAN_PATH
    lineage_path = root / TASK_PLAN_LINEAGE_PATH
    if not plan_path.is_file() or not lineage_path.is_file():
        missing = [str(path) for path in (plan_path, lineage_path) if not path.is_file()]
        return (
            None,
            None,
            [
                Diagnostic(
                    "task_plan_bundle_incomplete",
                    "The TaskPlan and its lineage must be emitted as one transaction.",
                    detail={"missing": missing},
                )
            ],
        )
    try:
        actual_plan = load_json(plan_path)
        actual_lineage = load_json(lineage_path)
        expected_plan = build_task_plan(root, plan, records)
        expected_lineage = build_task_plan_lineage(root, records, expected_plan)
    except (OSError, ValueError, KeyError) as error:
        return None, None, [Diagnostic("task_plan_bundle_invalid", str(error))]
    diagnostics: list[Diagnostic] = []
    if actual_plan != expected_plan:
        diagnostics.append(
            Diagnostic(
                "task_plan_projection_mismatch",
                "TaskPlan differs from the current reviewed Seamwise projection.",
                str(plan_path),
            )
        )
    if actual_lineage != expected_lineage:
        diagnostics.append(
            Diagnostic(
                "task_lineage_projection_mismatch",
                "TaskPlan lineage differs from the current intent, review, and unit projection.",
                str(lineage_path),
            )
        )
    return actual_plan, actual_lineage, diagnostics
