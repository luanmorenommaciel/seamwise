from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from conftest import git_init, write_recipe

from seamwise.cli import cli
from seamwise.engine import accept_plan, build_plan, compile_graph, map_recipe
from seamwise.io import UnsafeWriteTargetError, workspace_lock, workspace_lock_path
from seamwise.reporting import CONTEXT_PACKET_LIMIT, agent_context, build_report
from seamwise.workspace import init_workspace, status_result


def compile_reviewed(root: Path, recipe: dict[str, Any], *, fixture: bool = False) -> None:
    git_init(root)
    source = write_recipe(root, recipe)
    assert init_workspace(root).ok
    assert map_recipe(root, source).ok
    assert build_plan(root).exit_code == 2
    assert accept_plan(
        root, reviewer="pytest", reason="explicit regression review", fixture=fixture
    ).ok
    assert compile_graph(root).ok


def test_workspace_lock_uses_runtime_state_not_git_metadata(tmp_path: Path) -> None:
    git_init(tmp_path)
    lock = workspace_lock_path(tmp_path)
    assert not lock.is_relative_to(tmp_path / ".git")
    with workspace_lock(tmp_path):
        assert lock.is_file()
    assert not (tmp_path / ".git/seamwise").exists()


def test_workspace_lock_rejects_symlinked_runtime_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside-lock-home"
    outside.mkdir()
    linked_home = tmp_path / "linked-lock-home"
    linked_home.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("SEAMWISE_LOCK_HOME", str(linked_home))
    with (
        pytest.raises(UnsafeWriteTargetError, match="Unsafe workspace lock directory"),
        workspace_lock(tmp_path),
    ):
        pass
    assert list(outside.iterdir()) == []


def test_workspace_lock_rejects_symlinked_lock_file(tmp_path: Path) -> None:
    lock = workspace_lock_path(tmp_path)
    with workspace_lock(tmp_path):
        pass
    lock.unlink()
    outside = tmp_path / "outside-lock-file"
    outside.write_text("untouched", encoding="utf-8")
    lock.symlink_to(outside)
    with (
        pytest.raises(UnsafeWriteTargetError, match="Unsafe workspace lock file"),
        workspace_lock(tmp_path),
    ):
        pass
    assert outside.read_text(encoding="utf-8") == "untouched"


def test_status_and_agent_context_fail_closed_after_plan_tamper(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    plan = tmp_path / "seamwise/delivery-plan.yaml"
    plan.write_text(plan.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    status = status_result(tmp_path)
    context = agent_context(tmp_path, host="chat")
    assert status.exit_code == 4
    assert status.token == "STATUS=BLOCKED"
    assert status.data["task_graph"] is False
    assert any(item.code == "review_hash_mismatch" for item in status.diagnostics)
    assert context.token == "AGENT_CONTEXT=BLOCKED"


def test_malformed_starter_blocks_report_and_context_without_exceptions(tmp_path: Path) -> None:
    assert init_workspace(tmp_path).ok
    (tmp_path / "seamwise/intent.md").write_text("---\ninvalid: [\n", encoding="utf-8")
    context = agent_context(tmp_path, host="chat")
    report = build_report(tmp_path, output_format="json")
    assert context.token == "AGENT_CONTEXT=BLOCKED"
    assert report.token == "REPORT=BLOCKED"


def test_pre_map_chat_packet_contains_the_recipe_contract(tmp_path: Path) -> None:
    assert init_workspace(tmp_path).ok
    result = agent_context(tmp_path, host="chat")
    packet = result.data["packet"]
    assert result.ok
    assert '"recipe_authoring"' in packet
    assert '"mode": "guided-one-pass"' in packet
    assert "Ask exactly one concise unanswered question at a time" in packet
    assert '"example_yaml"' not in packet


def test_post_compile_chat_packet_contains_reviewed_task_plan(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    result = agent_context(tmp_path, host="chat")
    packet = result.data["packet"]
    assert result.ok
    assert '"id": "T-20260802-request-101"' in packet
    assert '"task_plan_lineage"' in packet
    assert "pytest -q tests/test_request_101.py" in packet


def test_chat_packet_enforces_final_serialized_byte_limit(tmp_path: Path) -> None:
    assert init_workspace(tmp_path).ok
    intent = tmp_path / "seamwise/intent.md"
    intent.write_text(
        intent.read_text(encoding="utf-8") + "\n" + ("oversized-evidence " * 50_000),
        encoding="utf-8",
    )
    result = agent_context(tmp_path, host="chat")
    packet = result.data["packet"]
    assert len(packet.encode("utf-8")) <= CONTEXT_PACKET_LIMIT
    assert "Field omitted to keep the portable packet" in packet


def test_review_receipt_must_be_complete_and_schema_valid(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    git_init(tmp_path)
    source = write_recipe(tmp_path, recipe)
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    assert build_plan(tmp_path).exit_code == 2
    plan = tmp_path / "seamwise/delivery-plan.yaml"
    receipt = tmp_path / "seamwise/reviews/delivery-plan-review.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps({"plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest()}),
        encoding="utf-8",
    )
    result = compile_graph(tmp_path)
    assert result.exit_code == 4
    assert any(item.code == "review_schema" for item in result.diagnostics)


def test_review_fixture_class_is_hash_bound_and_cannot_be_recompiled_away(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    receipt_path = tmp_path / "seamwise/reviews/delivery-plan-review.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["fixture"] = False
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    result = compile_graph(tmp_path)
    assert result.exit_code == 4
    assert any(item.code == "review_authority_hash_mismatch" for item in result.diagnostics)


def test_task_plan_tamper_invalidates_lineage_projection(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    task_plan = tmp_path / "seamwise/task-plan.json"
    value = json.loads(task_plan.read_text(encoding="utf-8"))
    value["metadata"]["name"] = "tampered"
    task_plan.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    status = status_result(tmp_path)
    assert status.exit_code == 4
    assert any(item.code == "task_plan_projection_mismatch" for item in status.diagnostics)


def test_force_init_only_replaces_two_starter_documents(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    preserved = [
        tmp_path / "seamwise/evidence.jsonl",
        tmp_path / "seamwise/seam-map.yaml",
        tmp_path / "seamwise/delivery-plan.yaml",
        tmp_path / "seamwise/reviews/delivery-plan-review.json",
        tmp_path / "seamwise/task-plan.json",
        tmp_path / "seamwise/task-plan-lineage.json",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in preserved}
    assert init_workspace(tmp_path, force=True).ok
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in preserved} == before


def test_json_usage_errors_are_exactly_one_envelope(tmp_path: Path) -> None:
    runner = CliRunner()
    for arguments in (
        ["--workspace", str(tmp_path), "--json", "map"],
        ["--workspace", str(tmp_path), "--json", "does-not-exist"],
    ):
        result = runner.invoke(cli, arguments)
        assert result.exit_code == 3
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["token"] == "CLI=INVALID"


def test_plain_status_and_inspect_render_useful_data(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    runner = CliRunner()
    status = runner.invoke(cli, ["--workspace", str(tmp_path), "status"])
    inspect = runner.invoke(
        cli,
        ["--workspace", str(tmp_path), "inspect", "T-20260802-request-101"],
    )
    assert status.exit_code == 0
    assert '"task_graph": true' in status.stdout
    assert inspect.exit_code == 0
    assert '"seam": "SEAM-REQUEST-ENFORCEMENT"' in inspect.stdout
