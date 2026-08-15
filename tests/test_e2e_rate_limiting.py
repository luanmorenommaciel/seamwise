from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner
from conftest import compile_fixture, git_init, write_recipe

from seamwise.cli import cli
from seamwise.engine import accept_plan, build_plan, compile_graph, inspect_lineage, map_recipe
from seamwise.reporting import build_report
from seamwise.workspace import init_workspace, stage_state, status_result


def test_rate_limiting_compiles_to_valid_unsealed_task_dag(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    git_init(tmp_path)
    source = write_recipe(tmp_path, recipe)

    initialized = init_workspace(tmp_path)
    assert initialized.token == "WORKSPACE=READY"

    mapped = map_recipe(tmp_path, source)
    assert mapped.token == "SEAM_MAP=READY"
    assert mapped.data["seams"] == 4

    planned = build_plan(tmp_path)
    assert planned.token == "DELIVERY_PLAN=NEEDS_REVIEW"
    assert planned.exit_code == 2
    assert not (tmp_path / "seamwise/reviews/delivery-plan-review.json").exists()

    reviewed = accept_plan(
        tmp_path,
        reviewer="pytest-fixture",
        reason="Prove the canonical rate-limiting steel thread",
        fixture=True,
    )
    assert reviewed.token == "DELIVERY_PLAN=READY"

    compiled = compile_graph(tmp_path)
    assert compiled.token == "TASK_GRAPH=READY"
    assert compiled.data["tasks"] == 4

    graph = compiled.data["graph"]
    assert graph["critical_path"] == [
        "T-20260802-policy-schema",
        "T-20260802-effective-policy",
        "T-20260802-request-101",
        "T-20260802-decision-visibility",
    ]
    assert [edge["kind"] for edge in graph["edges"]] == [
        "depends_on",
        "depends_on",
        "depends_on",
    ]

    task_plan = json.loads((tmp_path / "seamwise/task-plan.json").read_text(encoding="utf-8"))
    assert task_plan["api_version"] == "taskspec.dev/v1"
    assert task_plan["metadata"]["name"] == "DI-RATE-LIMIT"
    assert task_plan["approved"] is True
    assert len(task_plan["units"]) == 4
    assert not (tmp_path / "tasks").exists()
    first_unit = next(
        unit for unit in task_plan["units"] if unit["id"] == "T-20260802-policy-schema"
    )
    expected_traceability = {
        "eval_1": ["B-1"],
        "eval_2": ["B-1"],
        "eval_3": ["B-2"],
    }
    assert {item["id"]: item["verifies"] for item in first_unit["evals"]} == (expected_traceability)
    assert first_unit["touches_paths"] == []
    assert first_unit["creates_paths"] == [
        "src/rate_limit/policy.schema.json",
        "tests/test_policy_schema.py",
    ]

    lineage = json.loads((tmp_path / "seamwise/task-plan-lineage.json").read_text(encoding="utf-8"))
    assert set(lineage["units"]) == {unit["id"] for unit in task_plan["units"]}
    assert all(item["seam"].startswith("SEAM-") for item in lineage["units"].values())
    assert all(item["swimlane"].startswith("LANE-") for item in lineage["units"].values())
    assert all(item["leg"].startswith("LEG-") for item in lineage["units"].values())

    traced = inspect_lineage(tmp_path, "T-20260802-decision-visibility")
    assert traced.data["leg"] == "LEG-DENIAL-REASON-VISIBLE"
    assert status_result(tmp_path).next_steps == [
        "Pass seamwise/task-plan.json and seamwise/task-plan-lineage.json to the composition coordinator."
    ]
    assert stage_state(tmp_path) == {
        "initialized": True,
        "seam_map": True,
        "delivery_plan": True,
        "reviewed": True,
        "task_graph": True,
        "task_plan": True,
        "task_plan_lineage": True,
        "task_specs": 0,
        "materialization_receipt": False,
        "units": 4,
        "dispatch_authorized": False,
        "issues": [],
    }

    report = build_report(tmp_path, output_format="html")
    assert report.ok
    assert "Derived report · never authorization" in report.artifacts[0].read_text(encoding="utf-8")


def test_prepare_rejects_changed_source_after_mapping(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    original_intent = (tmp_path / "seamwise/intent.md").read_text(encoding="utf-8")
    recipe["intent"]["title"] = "A revised delivery intent"
    revised = write_recipe(tmp_path, recipe)

    result = CliRunner().invoke(
        cli,
        [
            "--workspace",
            str(tmp_path),
            "--json",
            "prepare",
            "--source",
            str(revised),
        ],
    )
    assert result.exit_code == 4
    envelope = json.loads(result.stdout)
    assert envelope["token"] == "PREPARE=SOURCE_CHANGED"
    assert envelope["diagnostics"][0]["code"] == "source_recipe_changed"
    assert (tmp_path / "seamwise/intent.md").read_text(encoding="utf-8") == original_intent


def test_plan_rerun_preserves_a_current_hash_bound_review(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    assert build_plan(tmp_path).exit_code == 2
    assert accept_plan(tmp_path, reviewer="pytest", reason="accepted", fixture=True).ok
    result = build_plan(tmp_path)
    assert result.ok
    assert result.token == "DELIVERY_PLAN=READY"
    assert result.data["preserved_review"] is True


def test_task_rendering_does_not_recursively_expand_authored_placeholder_text(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["goal"] = "preserve-left {{GOAL_ONE_PARAGRAPH}} preserve-right"
    task["done_condition"] = "DONE-CONDITION-SENTINEL"
    task["evals"][0]["bash"] = "printf '%s' '{{EVAL_2_BASH}}' >/dev/null"
    second_bash = task["evals"][1]["bash"]

    assert compile_fixture(tmp_path, recipe).ok
    plan = json.loads((tmp_path / "seamwise/task-plan.json").read_text(encoding="utf-8"))
    unit = next(item for item in plan["units"] if item["id"] == task["id"])
    assert unit["goal"] == "preserve-left {{GOAL_ONE_PARAGRAPH}} preserve-right"
    assert unit["evals"][0]["command"] == "printf '%s' '{{EVAL_2_BASH}}' >/dev/null"
    assert [item["command"] for item in unit["evals"]].count(second_bash) == 1


def test_yaml_ambiguous_backend_or_tool_names_are_rejected(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["execution_backend"] = "null"
    task["required_tools"] = ["git", "true", "no"]
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 3
    assert any(item.code == "yaml_scalar_ambiguous" for item in result.diagnostics)


def test_l_effort_glm_backend_survives_task_plan_projection(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["effort"] = "L"
    task["execution_backend"] = "glm"
    assert compile_fixture(tmp_path, recipe).ok
    plan = json.loads((tmp_path / "seamwise/task-plan.json").read_text(encoding="utf-8"))
    unit = next(item for item in plan["units"] if item["id"] == task["id"])
    assert unit["execution_backend"] == "glm"
