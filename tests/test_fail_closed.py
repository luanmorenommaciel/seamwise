from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner
from conftest import compile_fixture, write_recipe

from seamwise.cli import cli
from seamwise.engine import (
    accept_plan,
    build_plan,
    compile_graph,
    map_recipe,
    render_graph_mermaid,
)
from seamwise.reporting import build_report
from seamwise.taskpack import task_pack_root
from seamwise.workspace import init_workspace, status_result


def test_missing_evidence_needs_discovery(tmp_path: Path, recipe: dict[str, Any]) -> None:
    recipe["evidence"] = []
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.token == "SEAM_MAP=NEEDS_DISCOVERY"
    assert result.exit_code == 2
    assert not (tmp_path / "seamwise/seam-map.yaml").exists()


def test_recipe_duplicate_authority_keys_are_rejected(tmp_path: Path) -> None:
    source_text = (Path(__file__).parents[1] / "examples/rate-limiting/recipe.yaml").read_text(
        encoding="utf-8"
    )
    source_text = source_text.replace(
        "    owner: platform-contracts\n",
        "    owner: hidden-owner\n    owner: platform-contracts\n",
        1,
    )
    source = tmp_path / "duplicate-owner.yaml"
    source.write_text(source_text, encoding="utf-8")
    result = map_recipe(tmp_path, source)
    assert result.exit_code == 3
    assert any(item.code == "recipe_unreadable" for item in result.diagnostics)


def test_local_evidence_must_exist_and_match_its_declared_hash(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    for record in [recipe["intent"]["source"], recipe["evidence"][0]["source"]]:
        record["uri"] = "evidence/blueprint.pdf"
    source = write_recipe(tmp_path, recipe)

    missing = map_recipe(tmp_path, source)
    assert missing.exit_code == 2
    assert any(item.code == "local_source_unavailable" for item in missing.diagnostics)

    evidence = tmp_path / "evidence/blueprint.pdf"
    evidence.parent.mkdir()
    evidence.write_bytes(b"wrong bytes")
    tampered = map_recipe(tmp_path, source)
    assert tampered.exit_code == 4
    assert any(item.code == "local_source_hash_mismatch" for item in tampered.diagnostics)


def test_remote_evidence_requires_a_local_immutable_snapshot(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    recipe["evidence"][0]["source"]["uri"] = "https://example.invalid/unavailable-evidence"
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.token == "SEAM_MAP=NEEDS_DISCOVERY"
    assert result.exit_code == 2
    assert any(item.code == "remote_source_unverified" for item in result.diagnostics)
    assert not (tmp_path / "seamwise/seam-map.yaml").exists()


def test_unsupported_behavior_and_eval_ids_are_rejected_by_contract(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["behavior"][0]["id"] = "B-7"
    task["evals"][0]["id"] = "eval_7"
    task["evals"][0]["verifies"] = ["B-7"]
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.token == "SEAM_MAP=ERROR"
    assert result.exit_code == 3
    assert any(item.code == "recipe_schema" for item in result.diagnostics)


def test_missing_owner_needs_owner_input(tmp_path: Path, recipe: dict[str, Any]) -> None:
    recipe["seams"][0]["owner"] = ""
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.token == "SEAM_MAP=NEEDS_OWNER_INPUT"
    assert result.exit_code == 2


def test_unaccepted_decision_closes_gate(tmp_path: Path, recipe: dict[str, Any]) -> None:
    recipe["decisions"][0]["status"] = "proposed"
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.token == "SEAM_MAP=NEEDS_ARCHITECTURE_DECISION"
    assert result.exit_code == 2


def test_system_map_unknowns_close_the_delivery_plan_gate(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    recipe["system_map"]["unknowns"] = ["Production counter ownership is undecided"]
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok

    result = build_plan(tmp_path)
    assert result.token == "DELIVERY_PLAN=NEEDS_ARCHITECTURE_DECISION"
    assert result.exit_code == 2
    assert any(item.code == "architecture_unknown_open" for item in result.diagnostics)
    assert not (tmp_path / "seamwise/delivery-plan.yaml").exists()
    assert list((tmp_path / "seamwise/swimlanes").iterdir()) == []
    assert list((tmp_path / "seamwise/legs").iterdir()) == []


def test_blank_capability_state_or_objection_summary_closes_mapping(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    recipe["seams"][0]["swimlane"]["legs"][0]["observable_state"] = "   "
    recipe["objections"][0]["summary"] = "   "
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.token == "SEAM_MAP=NEEDS_DISCOVERY"
    assert result.exit_code == 2
    assert sum(item.code == "missing_evidence" for item in result.diagnostics) >= 2


@pytest.mark.parametrize(
    "field_path",
    (
        ("intent", "title"),
        ("intent", "success", 0),
        ("system_map", "components", 0),
        ("seams", 0, "name"),
        ("seams", 0, "description"),
        ("seams", 0, "consumes", 0),
        ("seams", 0, "rejected_alternatives", 0, "reason"),
        ("seams", 0, "swimlane", "name"),
        ("seams", 0, "swimlane", "legs", 0, "produces", 0),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "title"),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "goal"),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "done_condition"),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "behavior", 0, "given"),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "evals", 0, "description"),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "evals", 0, "bash"),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "anti_patterns", 0, "reason"),
        ("seams", 0, "swimlane", "legs", 0, "tasks", 0, "observability"),
    ),
)
def test_authored_semantic_text_must_be_nonblank(
    tmp_path: Path, recipe: dict[str, Any], field_path: tuple[str | int, ...]
) -> None:
    cursor: Any = recipe
    for segment in field_path[:-1]:
        cursor = cursor[segment]
    cursor[field_path[-1]] = "   \t"

    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))

    assert not result.ok
    assert any(
        item.code == "blank_authored_text" and item.detail.get("field")
        for item in result.diagnostics
    )
    assert not (tmp_path / "seamwise/seam-map.yaml").exists()


def test_open_objection_cannot_be_reviewed(tmp_path: Path, recipe: dict[str, Any]) -> None:
    recipe["objections"][0]["status"] = "OPEN"
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    plan = build_plan(tmp_path)
    assert plan.token == "DELIVERY_PLAN=OPEN_OBJECTIONS"
    review = accept_plan(tmp_path, reviewer="pytest", reason="must fail")
    assert review.token == "DELIVERY_PLAN=OPEN_OBJECTIONS"
    assert review.exit_code == 2


def test_seam_tamper_blocks_planning(tmp_path: Path, recipe: dict[str, Any]) -> None:
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    seam = tmp_path / "seamwise/seams/SEAM-POLICY-CONTRACT.md"
    seam.write_text(seam.read_text(encoding="utf-8") + "\ntamper\n", encoding="utf-8")
    result = build_plan(tmp_path)
    assert result.exit_code == 4
    assert any(item.code == "seam_hash_mismatch" for item in result.diagnostics)


def test_review_hash_tamper_blocks_compilation(tmp_path: Path, recipe: dict[str, Any]) -> None:
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    assert build_plan(tmp_path).exit_code == 2
    assert accept_plan(tmp_path, reviewer="pytest", reason="fixture", fixture=True).ok
    plan = tmp_path / "seamwise/delivery-plan.yaml"
    plan.write_text(plan.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")
    result = compile_graph(tmp_path, task_pack_root=task_pack_root())
    assert result.token == "TASK_GRAPH=BLOCKED"
    assert result.exit_code == 4
    assert any(item.code == "review_hash_mismatch" for item in result.diagnostics)


def test_cycle_has_stable_failure_token(tmp_path: Path, recipe: dict[str, Any]) -> None:
    first = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    first["depends_on"] = ["T-20260802-decision-visibility"]
    result = compile_fixture(tmp_path, recipe)
    assert result.token == "TASK_GRAPH=CYCLE"
    assert result.exit_code == 4


def test_unordered_write_collision_has_stable_token(tmp_path: Path, recipe: dict[str, Any]) -> None:
    first = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    second = recipe["seams"][1]["swimlane"]["legs"][0]["tasks"][0]
    second["depends_on"] = []
    recipe["seams"][1]["swimlane"]["legs"][0]["requires"] = []
    second["creates_paths"] = list(first["creates_paths"])
    result = compile_fixture(tmp_path, recipe)
    assert result.token == "TASK_GRAPH=COLLISION"
    assert result.exit_code == 4


def test_ancestor_write_collision_is_not_mistaken_for_parallel_work(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    first = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    fourth = recipe["seams"][3]["swimlane"]["legs"][0]["tasks"][0]
    fourth["depends_on"] = []
    recipe["seams"][3]["swimlane"]["legs"][0]["requires"] = []
    first["creates_paths"] = ["src/policy"]
    fourth["creates_paths"] = ["src/policy/runtime.py"]
    result = compile_fixture(tmp_path, recipe)
    assert result.token == "TASK_GRAPH=COLLISION"
    assert result.exit_code == 4
    assert any(item.code == "path_collision" for item in result.diagnostics)


def test_glob_write_paths_are_rejected_during_mapping(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["creates_paths"] = ["src/*.py"]
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 3
    assert any(item.code == "noncanonical_project_path" for item in result.diagnostics)


def test_required_capability_state_needs_a_real_task_dependency(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    consumer = recipe["seams"][1]["swimlane"]["legs"][0]["tasks"][0]
    consumer["depends_on"] = []
    result = compile_fixture(tmp_path, recipe)
    assert result.token == "TASK_GRAPH=UNPROVABLE_NODE"
    assert result.exit_code == 4
    assert any(item.code == "missing_capability_dependency" for item in result.diagnostics)


def test_unknown_required_capability_state_cannot_erase_the_dependency_gate(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    leg = recipe["seams"][1]["swimlane"]["legs"][0]
    leg["requires"] = ["misspelled state with no producer"]
    leg["tasks"][0]["depends_on"] = []
    result = compile_fixture(tmp_path, recipe)
    assert result.token == "TASK_GRAPH=UNPROVABLE_NODE"
    assert any(item.code == "capability_requirement_unproduced" for item in result.diagnostics)


def test_capability_leg_outside_steel_thread_still_needs_task_causality(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    leg = recipe["seams"][3]["swimlane"]["legs"][0]
    recipe["steel_thread"].remove(leg["id"])
    leg["tasks"][0]["depends_on"] = []
    result = compile_fixture(tmp_path, recipe)
    assert result.token == "TASK_GRAPH=UNPROVABLE_NODE"
    assert any(item.code == "missing_capability_dependency" for item in result.diagnostics)


def test_write_surface_cannot_overlap_do_not_touch_boundary(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["do_not_touch"] = ["src/rate_limit"]
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 3
    assert any(item.code == "forbidden_write_overlap" for item in result.diagnostics)


def test_touch_path_must_exist_or_be_created_by_an_ancestor(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["touches_paths"] = ["src/rate_limit/typo.py"]
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 4
    assert any(item.code == "touch_path_unprovable" for item in result.diagnostics)


def test_create_path_must_not_already_exist(tmp_path: Path, recipe: dict[str, Any]) -> None:
    existing = tmp_path / "src/rate_limit/policy.schema.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("owned", encoding="utf-8")
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 4
    assert any(item.code == "create_path_already_exists" for item in result.diagnostics)


def test_write_path_cannot_cross_project_symlink(tmp_path: Path, recipe: dict[str, Any]) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src/link").symlink_to(outside, target_is_directory=True)
    task = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    task["creates_paths"][0] = "src/link/escaped.json"

    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 4
    assert any(item.code == "write_path_symlink_escape" for item in result.diagnostics)
    assert list(outside.iterdir()) == []


def test_write_paths_cannot_differ_only_by_case(tmp_path: Path, recipe: dict[str, Any]) -> None:
    first = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    second = recipe["seams"][1]["swimlane"]["legs"][0]["tasks"][0]
    first["creates_paths"] = ["src/Policy.py"]
    second["creates_paths"] = ["src/policy.py"]
    result = map_recipe(tmp_path, write_recipe(tmp_path, recipe))
    assert result.exit_code == 4
    assert any(item.code == "case_portability_collision" for item in result.diagnostics)


def test_write_surface_over_budget_is_unprovable(tmp_path: Path, recipe: dict[str, Any]) -> None:
    first = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]
    first["effort"] = "XS"
    result = compile_fixture(tmp_path, recipe)
    assert result.token == "TASK_GRAPH=UNPROVABLE_NODE"
    assert result.exit_code == 4
    assert any(item.code == "write_surface_too_large" for item in result.diagnostics)


def test_dry_run_writes_nothing(tmp_path: Path, recipe: dict[str, Any]) -> None:
    source = write_recipe(tmp_path, recipe)
    initialized = init_workspace(tmp_path, dry_run=True)
    assert initialized.ok
    assert initialized.artifacts
    assert not (tmp_path / "seamwise").exists()
    mapped = map_recipe(tmp_path, source, dry_run=True)
    assert mapped.ok
    assert mapped.artifacts
    assert not (tmp_path / "seamwise").exists()


def test_init_refuses_symlinked_managed_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "seamwise").symlink_to(outside, target_is_directory=True)

    result = init_workspace(root)
    assert result.token == "WORKSPACE=BLOCKED"
    assert result.exit_code == 4
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "relative",
    (
        "seamwise",
        "seamwise/decisions",
        "seamwise/seams",
        "seamwise/swimlanes",
        "seamwise/legs",
        "seamwise/reviews",
        "tasks",
        "telemetry",
        "reports",
        "lessons",
    ),
)
def test_init_refuses_regular_file_in_managed_directory_slot(tmp_path: Path, relative: str) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    slot = root / relative
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text("not a directory", encoding="utf-8")

    result = init_workspace(root)
    assert result.token == "WORKSPACE=BLOCKED"
    assert result.exit_code == 4
    assert any(item.artifact == str(slot) for item in result.diagnostics)


def test_cli_refuses_regular_file_workspace_without_mechanism_failure(tmp_path: Path) -> None:
    workspace = tmp_path / "not-a-workspace"
    workspace.write_text("file", encoding="utf-8")
    result = CliRunner().invoke(
        cli,
        ["--workspace", str(workspace), "--json", "status"],
    )
    assert result.exit_code == 3
    envelope = json.loads(result.stdout)
    assert envelope["token"] == "CLI=INVALID"
    assert envelope["diagnostics"][0]["code"] == "usage_error"


def test_map_refuses_symlinked_managed_descendant(tmp_path: Path, recipe: dict[str, Any]) -> None:
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    outside.mkdir()
    assert init_workspace(root).ok
    seam_directory = root / "seamwise/seams"
    seam_directory.rmdir()
    seam_directory.symlink_to(outside, target_is_directory=True)

    result = map_recipe(root, write_recipe(root, recipe))
    assert result.exit_code == 4
    assert any(item.code == "unsafe_managed_path" for item in result.diagnostics)
    assert list(outside.iterdir()) == []


def test_map_never_replaces_directory_at_managed_file_output(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    root = tmp_path / "workspace"
    assert init_workspace(root).ok
    seam_map = root / "seamwise/seam-map.yaml"
    seam_map.unlink()
    seam_map.mkdir()
    valuable = seam_map / "valuable.txt"
    valuable.write_text("preserve me", encoding="utf-8")

    result = map_recipe(root, write_recipe(root, recipe))
    assert result.exit_code == 4
    assert any(item.code == "unsafe_write_target" for item in result.diagnostics)
    assert valuable.read_text(encoding="utf-8") == "preserve me"
    assert list((root / "seamwise/seams").iterdir()) == []
    assert not list((root / "seamwise").glob(".seam-map.yaml.seamwise-backup-*"))


def test_compile_refuses_symlinked_output_root(tmp_path: Path, recipe: dict[str, Any]) -> None:
    root = tmp_path / "workspace"
    outside_tasks = tmp_path / "outside-tasks"
    outside_tasks.mkdir()
    assert init_workspace(root).ok
    source = write_recipe(root, recipe)
    assert map_recipe(root, source).ok
    assert build_plan(root).exit_code == 2
    assert accept_plan(root, reviewer="pytest", reason="boundary test", fixture=True).ok
    (root / "tasks/task-graph.yaml").unlink()
    (root / "tasks").rmdir()
    (root / "tasks").symlink_to(outside_tasks, target_is_directory=True)
    compile_result = compile_graph(root, task_pack_root=task_pack_root())
    assert compile_result.exit_code == 4
    assert list(outside_tasks.iterdir()) == []


def test_report_refuses_symlinked_output_root(tmp_path: Path, recipe: dict[str, Any]) -> None:
    root = tmp_path / "workspace"
    outside_reports = tmp_path / "outside-reports"
    outside_reports.mkdir()
    assert compile_fixture(root, recipe).ok

    (root / "reports").rmdir()
    (root / "reports").symlink_to(outside_reports, target_is_directory=True)
    report = build_report(root, output_format="json")
    assert report.exit_code == 4
    assert any(item.artifact == str(root / "reports") for item in report.diagnostics)
    assert list(outside_reports.iterdir()) == []


def test_mermaid_projection_escapes_hostile_authored_titles() -> None:
    rendered = render_graph_mermaid(
        {
            "nodes": [
                {
                    "id": "T-safe",
                    "title": 'ok"] --> EVIL["oops\nflowchart TD',
                }
            ],
            "edges": [],
        }
    )
    assert len(rendered.splitlines()) == 2
    assert "--> EVIL" not in rendered
    assert "&#34;" in rendered
    assert "&#93;" in rendered


def test_coordinated_projection_rebinding_cannot_erase_reviewed_tasks(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    assert compile_fixture(tmp_path, recipe).ok
    graph_path = tmp_path / "tasks/task-graph.yaml"
    graph = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
    graph["nodes"] = []
    graph["edges"] = []
    graph["critical_path"] = []
    mermaid = "flowchart LR\n"
    graph["critical_path_mermaid_sha256"] = hashlib.sha256(mermaid.encode("utf-8")).hexdigest()
    graph_path.write_text(yaml.safe_dump(graph, sort_keys=False), encoding="utf-8")
    (tmp_path / "tasks/critical-path.mmd").write_text(mermaid, encoding="utf-8")
    lineage_path = tmp_path / "tasks/task-lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage["tasks"] = {}
    lineage_path.write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8")
    for spec in (tmp_path / "tasks").glob("T-*.md"):
        spec.unlink()

    status = status_result(tmp_path)
    assert status.token == "STATUS=BLOCKED"
    assert status.exit_code == 4
    assert any(
        item.code in {"task_graph_projection_mismatch", "task_lineage_projection_mismatch"}
        for item in status.diagnostics
    )


def test_recipe_example_refuses_symlinked_output_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "redirect").symlink_to(outside, target_is_directory=True)
    result = CliRunner().invoke(
        cli,
        [
            "--workspace",
            str(root),
            "recipe",
            "example",
            "--output",
            "redirect/recipe.yaml",
        ],
    )
    assert result.exit_code == 4
    assert list(outside.iterdir()) == []
