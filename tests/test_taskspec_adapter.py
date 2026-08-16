from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner
from conftest import git_init, write_recipe

from seamwise.cli import cli
from seamwise.engine import accept_plan, build_plan, compile_graph, map_recipe
from seamwise.io import canonical_json, sha256_bytes, sha256_file
from seamwise.workspace import init_workspace, status_result


def reviewed_plan(root: Path, recipe: dict[str, Any]) -> None:
    git_init(root)
    source = write_recipe(root, recipe)
    assert init_workspace(root).ok
    assert map_recipe(root, source).ok
    assert build_plan(root).exit_code == 2
    assert accept_plan(root, reviewer="pytest", reason="projection boundary", fixture=True).ok


def test_compile_never_requires_or_invokes_taskspec(
    tmp_path: Path, recipe: dict[str, Any], monkeypatch: Any
) -> None:
    reviewed_plan(tmp_path, recipe)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("SEAMWISE_TASKSPEC_BIN", "/does/not/exist")
    result = compile_graph(tmp_path)
    assert result.ok
    assert result.token == "TASK_GRAPH=READY"
    assert {path.relative_to(tmp_path).as_posix() for path in result.artifacts} == {
        "seamwise/task-plan.json",
        "seamwise/task-plan-lineage.json",
    }
    assert not (tmp_path / "tasks").exists()
    assert not (tmp_path / "seamwise/task-materialization-receipt.json").exists()


def test_capabilities_are_machine_negotiable(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["--workspace", str(tmp_path), "--json", "capabilities"])
    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["contract"] == "SeamwiseCLIResult/v1"
    assert envelope["engine_version"] == "0.2.0"
    capability = envelope["data"]
    assert capability["contract"] == "SeamwiseCapabilities/v1"
    assert capability["contracts"]["task_plan"] == "TaskPlan/v1"
    assert capability["contracts"]["task_plan_lineage"] == ("SeamwiseTaskPlanLineage/v1")
    assert "task_materialization_receipt" not in capability["contracts"]
    assert capability["materializes_tasks"] is False
    assert capability["dispatch_authority"] is False


def test_taskplan_edit_invalidates_seamwise_lineage_binding(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    reviewed_plan(tmp_path, recipe)
    assert compile_graph(tmp_path).ok
    plan_path = tmp_path / "seamwise/task-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["metadata"]["name"] = "changed-after-review"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = status_result(tmp_path)
    assert status.token == "STATUS=BLOCKED"
    assert any(item.code == "task_plan_projection_mismatch" for item in status.diagnostics)


def test_lineage_binds_review_and_canonical_taskplan_digest(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    reviewed_plan(tmp_path, recipe)
    assert compile_graph(tmp_path).ok
    plan = json.loads((tmp_path / "seamwise/task-plan.json").read_text(encoding="utf-8"))
    lineage = json.loads((tmp_path / "seamwise/task-plan-lineage.json").read_text(encoding="utf-8"))
    review_path = tmp_path / "seamwise/reviews/delivery-plan-review.json"
    assert lineage["review"]["sha256"] == sha256_file(review_path)
    assert lineage["task_plan"]["digest"] == sha256_bytes(canonical_json(plan).encode("utf-8"))
    assert set(lineage["units"]) == {unit["id"] for unit in plan["units"]}
    assert all(entry["intent"] == lineage["intent"]["id"] for entry in lineage["units"].values())


def test_seamwise_distribution_has_no_embedded_taskspec_engine() -> None:
    repository = Path(__file__).resolve().parents[1]
    pyproject = (repository / "pyproject.toml").read_text(encoding="utf-8")
    assert 'task-spec = "seamwise.task_spec_cli:main"' not in pyproject
    assert not (repository / "src/seamwise/taskpack.py").exists()
    assert not (repository / "src/seamwise/task_spec_cli.py").exists()
    assert not (repository / "skills/task-spec").exists()
    assert not (repository / "vendor/task-pack-source.json").exists()
