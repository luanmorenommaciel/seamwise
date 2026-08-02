from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner
from conftest import compile_fixture, git_init, write_recipe

from seamwise.cli import cli
from seamwise.engine import accept_plan, build_plan, compile_graph, inspect_lineage, map_recipe
from seamwise.reporting import build_report
from seamwise.taskpack import task_pack_root, validate_task_specs
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

    compiled = compile_graph(tmp_path, task_pack_root=task_pack_root())
    assert compiled.token == "TASK_GRAPH=READY"
    assert compiled.data["tasks"] == 4

    graph = yaml.safe_load((tmp_path / "tasks/task-graph.yaml").read_text(encoding="utf-8"))
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

    validated = validate_task_specs(tmp_path)
    assert validated.token == "TASK_SPECS=VALID"
    assert validated.data["count"] == 4

    specs = sorted((tmp_path / "tasks").glob("T-*.md"))
    assert len(specs) == 4
    for spec in specs:
        text = spec.read_text(encoding="utf-8")
        assert "signed_off: false" in text
        assert "accepted: false" in text
        assert "delivery_intent: DI-RATE-LIMIT" in text

    first_card = (
        (tmp_path / "tasks/T-20260802-policy-schema.md")
        .read_text(encoding="utf-8")
        .split("## Validation Card", 1)[1]
    )
    expected_traceability = {
        "eval_1": "[B-1]",
        "eval_2": "[B-1]",
        "eval_3": "[B-2]",
    }
    for eval_id, verifies in expected_traceability.items():
        entry = first_card.split(f"- id: {eval_id}", 1)[1].split("terminal: true", 1)[0]
        assert f"verifies: {verifies}" in entry
    first_text = (tmp_path / "tasks/T-20260802-policy-schema.md").read_text(encoding="utf-8")
    assert "# Define the versioned rate-limit policy schema" in first_text
    assert '# "Define the versioned rate-limit policy schema"' not in first_text
    first_frontmatter = yaml.safe_load(first_text[4:].split("\n---\n", 1)[0])
    assert first_frontmatter["touches_paths"] == []
    assert first_frontmatter["creates_paths"] == [
        "src/rate_limit/policy.schema.json",
        "tests/test_policy_schema.py",
    ]

    lineage = json.loads((tmp_path / "tasks/task-lineage.json").read_text(encoding="utf-8"))
    assert set(lineage["tasks"]) == {path.stem for path in specs}
    assert all(item["seam"].startswith("SEAM-") for item in lineage["tasks"].values())
    assert all(item["swimlane"].startswith("LANE-") for item in lineage["tasks"].values())
    assert all(item["leg"].startswith("LEG-") for item in lineage["tasks"].values())

    traced = inspect_lineage(tmp_path, "T-20260802-decision-visibility")
    assert traced.data["leg"] == "LEG-DENIAL-REASON-VISIBLE"
    assert status_result(tmp_path).next_steps == [
        "seamwise tasks preflight --acknowledge-eval-execution"
    ]
    assert stage_state(tmp_path) == {
        "initialized": True,
        "seam_map": True,
        "delivery_plan": True,
        "reviewed": True,
        "task_graph": True,
        "task_specs": 4,
        "validated": True,
        "preflight_ready": False,
        "sealed_task_specs": 0,
        "claimed_sealed_task_specs": 0,
        "authority_gaps": [],
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
    spec = tmp_path / "tasks/T-20260802-policy-schema.md"
    text = spec.read_text(encoding="utf-8")
    assert "preserve-left {{GOAL_ONE_PARAGRAPH}} preserve-right" in text
    assert "printf '%s' '{{EVAL_2_BASH}}' >/dev/null" in text
    assert text.count(second_bash) == 1


def test_yaml_ambiguous_backend_or_tool_names_are_rejected(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["execution_backend"] = "null"
    task["required_tools"] = ["git", "true", "no"]
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 3
    assert any(item.code == "yaml_scalar_ambiguous" for item in result.diagnostics)


def test_l_effort_glm_backend_survives_task_pack_validation(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["effort"] = "L"
    task["execution_backend"] = "glm"
    assert compile_fixture(tmp_path, recipe).ok
    result = validate_task_specs(tmp_path)
    assert result.ok
    frontmatter = yaml.safe_load(
        (tmp_path / "tasks/T-20260802-policy-schema.md")
        .read_text(encoding="utf-8")[4:]
        .split("\n---\n", 1)[0]
    )
    assert frontmatter["execution_backend"] == "glm"


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="Task Pack PRE requires shellcheck")
def test_rate_limiting_preflight_is_ready_but_does_not_seal(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    git_init(tmp_path)
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    assert build_plan(tmp_path).exit_code == 2
    assert accept_plan(tmp_path, reviewer="pytest", reason="fixture", fixture=True).ok
    assert compile_graph(tmp_path, task_pack_root=task_pack_root()).ok

    preflight = validate_task_specs(tmp_path, preflight=True, execute_evals=True)
    assert preflight.token == "TASK_SPECS=PREFLIGHT_READY"
    for path in (tmp_path / "tasks").glob("T-*.md"):
        assert "signed_off: false" in path.read_text(encoding="utf-8")
