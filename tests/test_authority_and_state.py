from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from conftest import git_init, write_recipe

import seamwise.taskpack as taskpack_module
from seamwise.cli import cli
from seamwise.engine import accept_plan, build_plan, compile_graph, map_recipe
from seamwise.io import UnsafeWriteTargetError, workspace_lock, workspace_lock_path
from seamwise.reporting import CONTEXT_PACKET_LIMIT, agent_context, build_report
from seamwise.taskpack import setup_signing_key, task_pack_root, validate_task_specs
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
    assert compile_graph(root, task_pack_root=task_pack_root()).ok


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


def spec_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "tasks").glob("T-*.md"))
    }


def test_signing_key_setup_is_previewable_private_and_idempotent(tmp_path: Path) -> None:
    git_init(tmp_path)
    key = tmp_path / ".git/info/taskspec-signing-key"
    preview = setup_signing_key(tmp_path, dry_run=True)
    assert preview.token == "SIGNING_KEY=WOULD_CREATE"
    assert not key.exists()

    created = setup_signing_key(tmp_path)
    assert created.token == "SIGNING_KEY=READY"
    assert key.is_file()
    assert key.stat().st_mode & 0o777 == 0o600
    assert len(key.read_text(encoding="utf-8").strip()) == 64

    second = setup_signing_key(tmp_path)
    assert second.ok
    assert second.data["created"] is False


@pytest.mark.parametrize(
    ("content", "mode"),
    (
        ("", 0o600),
        ("not-hex" * 8, 0o600),
        ("a" * 64, 0o400),
        ("a" * 64, 0o700),
    ),
)
def test_signing_key_setup_rejects_invalid_existing_key(
    tmp_path: Path, content: str, mode: int
) -> None:
    git_init(tmp_path)
    key = tmp_path / ".git/info/taskspec-signing-key"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(content, encoding="utf-8")
    key.chmod(mode)

    result = setup_signing_key(tmp_path)
    assert result.token == "SIGNING_KEY=BLOCKED"
    assert any(item.code == "signing_key_permissions_invalid" for item in result.diagnostics)


def test_signing_key_setup_rejects_symlinked_key_path(tmp_path: Path) -> None:
    git_init(tmp_path)
    outside = tmp_path / "outside-key"
    outside.write_text("a" * 64, encoding="utf-8")
    key = tmp_path / ".git/info/taskspec-signing-key"
    key.symlink_to(outside)

    result = setup_signing_key(tmp_path, force=True)
    assert result.token == "SIGNING_KEY=BLOCKED"
    assert any(item.code == "unsafe_signing_key_path" for item in result.diagnostics)
    assert outside.read_text(encoding="utf-8") == "a" * 64


def test_signing_key_setup_rejects_symlinked_git_info_directory(tmp_path: Path) -> None:
    git_init(tmp_path)
    info = tmp_path / ".git/info"
    preserved = tmp_path / ".git/info-preserved"
    info.rename(preserved)
    outside = tmp_path / "outside-info"
    outside.mkdir()
    info.symlink_to(outside, target_is_directory=True)

    result = setup_signing_key(tmp_path)
    assert result.token == "SIGNING_KEY=BLOCKED"
    assert any(item.code == "unsafe_signing_key_path" for item in result.diagnostics)
    assert list(outside.iterdir()) == []


def rebind_task_hashes(root: Path) -> None:
    """Simulate an attacker updating every unkeyed hash after changing a spec."""

    lineage_path = root / "tasks/task-lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    hashes = spec_hashes(root)
    for task_id, entry in lineage["tasks"].items():
        entry["spec_sha256"] = hashes[f"{task_id}.md"]
    lineage_path.write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8")
    lineage_sha = hashlib.sha256(lineage_path.read_bytes()).hexdigest()
    for name in ("validation.json", "preflight.json"):
        receipt_path = root / "tasks" / name
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["lineage_sha256"] = lineage_sha
        receipt["specs"] = {Path(key).stem: value for key, value in hashes.items()}
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


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
    assert context.exit_code == 4
    assert context.token == "AGENT_CONTEXT=BLOCKED"


def test_malformed_starter_blocks_report_and_context_without_exceptions(
    tmp_path: Path,
) -> None:
    assert init_workspace(tmp_path).ok
    (tmp_path / "seamwise/intent.md").write_text("---\ninvalid: [\n", encoding="utf-8")

    context = agent_context(tmp_path, host="chat")
    report = build_report(tmp_path, output_format="json")
    assert context.exit_code == 4
    assert context.token == "AGENT_CONTEXT=BLOCKED"
    assert report.exit_code == 4
    assert report.token == "REPORT=BLOCKED"
    assert any(item.code == "workspace_starter_invalid" for item in context.diagnostics)


def test_pre_map_chat_packet_contains_the_recipe_contract(
    tmp_path: Path,
) -> None:
    assert init_workspace(tmp_path).ok
    result = agent_context(tmp_path, host="chat")
    packet = result.data["packet"]
    assert result.ok
    assert '"recipe_authoring"' in packet
    assert '"$schema": "https://json-schema.org/draft/2020-12/schema"' in packet
    assert '"mode": "guided-one-pass"' in packet
    assert "What observable delivery outcome should be true" in packet
    assert "Ask exactly one concise unanswered question at a time" in packet
    assert '"example_yaml"' not in packet
    assert "seamwise map --source <recipe.yaml>" in packet


def test_post_compile_chat_packet_contains_hash_bound_review_text(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    result = agent_context(tmp_path, host="chat")
    packet = result.data["packet"]
    assert result.ok
    assert '"verified_text_artifacts"' in packet
    assert "seamwise/legs/LEG-DENIAL-REASON-VISIBLE.md" in packet
    assert "tasks/T-20260802-request-101.md" in packet
    assert "signed_off: false" in packet
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
    assert result.ok
    assert len(packet.encode("utf-8")) <= CONTEXT_PACKET_LIMIT
    assert result.data["packet_bytes"] <= result.data["packet_limit"]
    assert "Field omitted to keep the portable packet" in packet
    assert packet.count("oversized-evidence") < 10


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

    result = compile_graph(tmp_path, task_pack_root=task_pack_root())
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

    result = compile_graph(tmp_path, task_pack_root=task_pack_root())
    assert result.exit_code == 4
    assert any(item.code == "review_authority_hash_mismatch" for item in result.diagnostics)
    lineage = json.loads((tmp_path / "tasks/task-lineage.json").read_text(encoding="utf-8"))
    assert lineage["fixture"] is True


def test_spec_tamper_invalidates_lineage_before_task_pack(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    spec = next((tmp_path / "tasks").glob("T-*.md"))
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "delivery_intent: DI-RATE-LIMIT", "delivery_intent: DI-FAKE"
        ),
        encoding="utf-8",
    )
    result = validate_task_specs(tmp_path)
    assert result.exit_code == 4
    assert any(item.code == "task_spec_hash_mismatch" for item in result.diagnostics)


def test_preflight_requires_ack_and_dry_run_does_not_execute_evals(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    first_eval = recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]["evals"][0]
    first_eval["bash"] = "touch dry-run-side-effect && false"
    compile_reviewed(tmp_path, recipe, fixture=True)

    missing_ack = validate_task_specs(tmp_path, preflight=True)
    preview = validate_task_specs(tmp_path, preflight=True, dry_run=True)
    assert missing_ack.exit_code == 2
    assert any(
        item.code == "eval_execution_acknowledgement_required" for item in missing_ack.diagnostics
    )
    assert preview.ok
    assert preview.token == "TASK_SPECS=VALID"
    assert not (tmp_path / "dry-run-side-effect").exists()
    assert not (tmp_path / "tasks/preflight.json").exists()


def test_fixture_cannot_be_sealed_and_cli_ack_is_required(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    before = spec_hashes(tmp_path)
    runner = CliRunner()
    no_ack = runner.invoke(
        cli,
        ["--workspace", str(tmp_path), "tasks", "seal", "--reviewer", "pytest"],
    )
    fixture = validate_task_specs(tmp_path, seal=True, reviewer="pytest")
    assert no_ack.exit_code == 2
    assert fixture.exit_code == 2
    assert any(
        item.code == "fixture_cannot_create_dispatch_authority" for item in fixture.diagnostics
    )
    assert spec_hashes(tmp_path) == before


@pytest.mark.skipif(
    taskpack_module.shutil.which("shellcheck") is None,
    reason="Task Pack PRE requires shellcheck",
)
def test_seal_without_signing_key_names_the_recovery_command(
    tmp_path: Path, recipe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    compile_reviewed(tmp_path, recipe)
    assert validate_task_specs(tmp_path).ok
    assert validate_task_specs(tmp_path, preflight=True, execute_evals=True).ok
    monkeypatch.delenv("TASKSPEC_SIGNING_KEY", raising=False)

    result = validate_task_specs(tmp_path, seal=True, reviewer="pytest", execute_evals=True)
    assert result.exit_code == 2
    assert any(item.code == "signing_key_unavailable" for item in result.diagnostics)
    assert result.next_steps == ["seamwise tasks setup-signing-key"]
    assert all(
        "signed_off: false" in path.read_text(encoding="utf-8")
        for path in (tmp_path / "tasks").glob("T-*.md")
    )


@pytest.mark.skipif(
    taskpack_module.shutil.which("shellcheck") is None,
    reason="Task Pack PRE requires shellcheck",
)
def test_tier1_seal_is_transactional_and_status_recognizes_it(
    tmp_path: Path, recipe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    compile_reviewed(tmp_path, recipe)
    assert validate_task_specs(tmp_path).ok
    assert validate_task_specs(tmp_path, preflight=True, execute_evals=True).ok
    monkeypatch.setenv("TASKSPEC_SIGNING_KEY", "pytest-tier1-key-material")

    preview_before = spec_hashes(tmp_path)
    preview = validate_task_specs(tmp_path, seal=True, reviewer="pytest", dry_run=True)
    assert preview.ok
    assert preview.token == "TASK_SPECS=VALID"
    assert spec_hashes(tmp_path) == preview_before

    missing_eval_ack = validate_task_specs(tmp_path, seal=True, reviewer="pytest")
    assert missing_eval_ack.exit_code == 2
    assert spec_hashes(tmp_path) == preview_before
    sealed = validate_task_specs(tmp_path, seal=True, reviewer="pytest", execute_evals=True)
    assert sealed.token == "TASK_SPECS=SEALED"
    assert sealed.ok
    assert all(
        "signed_off: true" in path.read_text(encoding="utf-8")
        and "signed_off_sig: hmac-sha256" in path.read_text(encoding="utf-8")
        for path in (tmp_path / "tasks").glob("T-*.md")
    )
    status = status_result(tmp_path)
    assert status.data["sealed_task_specs"] == 4
    assert status.data["validated"] is True
    assert status.data["preflight_ready"] is True
    assert "Tier-1-sealed" in status.next_steps[0]


@pytest.mark.skipif(
    taskpack_module.shutil.which("shellcheck") is None,
    reason="Task Pack PRE requires shellcheck",
)
def test_seal_requires_eval_ack_and_runs_only_the_pinned_stamp_gate_once(
    tmp_path: Path, recipe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe["seams"][0]["swimlane"]["legs"][0]["tasks"][0]["evals"][0]["bash"] = (
        "printf x >> seal-eval-count; false"
    )
    compile_reviewed(tmp_path, recipe)
    assert validate_task_specs(tmp_path).ok
    assert validate_task_specs(tmp_path, preflight=True, execute_evals=True).ok
    counter = tmp_path / "seal-eval-count"
    before = counter.read_text(encoding="utf-8")
    assert before
    monkeypatch.setenv("TASKSPEC_SIGNING_KEY", "pytest-tier1-key-material")

    missing_ack = validate_task_specs(tmp_path, seal=True, reviewer="pytest")
    assert missing_ack.exit_code == 2
    assert counter.read_text(encoding="utf-8") == before

    sealed = validate_task_specs(tmp_path, seal=True, reviewer="pytest", execute_evals=True)
    assert sealed.ok
    assert counter.read_text(encoding="utf-8") == before * 2


@pytest.mark.skipif(
    taskpack_module.shutil.which("shellcheck") is None,
    reason="Task Pack PRE requires shellcheck",
)
def test_status_rejects_forged_seal_even_when_unkeyed_hashes_are_rebound(
    tmp_path: Path, recipe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    compile_reviewed(tmp_path, recipe)
    assert validate_task_specs(tmp_path).ok
    assert validate_task_specs(tmp_path, preflight=True, execute_evals=True).ok
    monkeypatch.setenv("TASKSPEC_SIGNING_KEY", "pytest-tier1-key-material")
    assert validate_task_specs(tmp_path, seal=True, reviewer="pytest", execute_evals=True).ok

    spec = next((tmp_path / "tasks").glob("T-*.md"))
    content = spec.read_text(encoding="utf-8")
    spec.write_text(
        content.replace(
            "signed_off_sig: hmac-sha256-v2:", "signed_off_sig: hmac-sha256-v2:forged-"
        ),
        encoding="utf-8",
    )
    rebind_task_hashes(tmp_path)

    status = status_result(tmp_path)
    assert status.exit_code == 4
    assert status.token == "STATUS=BLOCKED"
    assert status.data["sealed_task_specs"] == 3
    assert status.data["claimed_sealed_task_specs"] == 4
    assert any(item.code == "tier1_signature_invalid" for item in status.diagnostics)
    assert "dispatch" not in status.next_steps[0].lower()


@pytest.mark.skipif(
    taskpack_module.shutil.which("shellcheck") is None,
    reason="Task Pack PRE requires shellcheck",
)
def test_status_keeps_missing_key_separate_from_integrity_corruption(
    tmp_path: Path, recipe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    compile_reviewed(tmp_path, recipe)
    assert validate_task_specs(tmp_path).ok
    assert validate_task_specs(tmp_path, preflight=True, execute_evals=True).ok
    monkeypatch.setenv("TASKSPEC_SIGNING_KEY", "pytest-tier1-key-material")
    assert validate_task_specs(tmp_path, seal=True, reviewer="pytest", execute_evals=True).ok
    monkeypatch.delenv("TASKSPEC_SIGNING_KEY")

    status = status_result(tmp_path)
    assert status.ok
    assert status.data["issues"] == []
    assert status.data["sealed_task_specs"] == 0
    assert status.data["claimed_sealed_task_specs"] == 4
    assert len(status.data["authority_gaps"]) == 4
    assert "signing key" in status.next_steps[0]
    assert "human supervision" in status.next_steps[0]


@pytest.mark.skipif(
    taskpack_module.shutil.which("shellcheck") is None,
    reason="Task Pack PRE requires shellcheck",
)
def test_failed_multi_spec_seal_never_changes_originals(
    tmp_path: Path, recipe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    compile_reviewed(tmp_path, recipe)
    assert validate_task_specs(tmp_path).ok
    assert validate_task_specs(tmp_path, preflight=True, execute_evals=True).ok
    monkeypatch.setenv("TASKSPEC_SIGNING_KEY", "pytest-tier1-key-material")
    before = spec_hashes(tmp_path)
    original_run = taskpack_module._run
    stamp_count = 0

    def fail_second_stamp(
        script: str, root: Path, arguments: list[str]
    ) -> subprocess.CompletedProcess[str]:
        nonlocal stamp_count
        if "--stamp" in arguments:
            stamp_count += 1
            if stamp_count == 2:
                return subprocess.CompletedProcess(arguments, 1, "", "injected stamp failure")
        return original_run(script, root, arguments)

    monkeypatch.setattr(taskpack_module, "_run", fail_second_stamp)
    result = validate_task_specs(tmp_path, seal=True, reviewer="pytest", execute_evals=True)
    assert result.exit_code == 4
    assert result.token == "TASK_SPECS=INVALID"
    assert spec_hashes(tmp_path) == before


def test_force_init_only_replaces_two_starter_documents(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    compile_reviewed(tmp_path, recipe, fixture=True)
    preserved = [
        tmp_path / "seamwise/evidence.jsonl",
        tmp_path / "seamwise/seam-map.yaml",
        tmp_path / "seamwise/delivery-plan.yaml",
        tmp_path / "seamwise/reviews/delivery-plan-review.json",
        tmp_path / "tasks/task-graph.yaml",
        tmp_path / "tasks/task-lineage.json",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in preserved}
    result = init_workspace(tmp_path, force=True)
    assert result.ok
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in preserved} == before


def test_json_usage_errors_are_exactly_one_envelope(tmp_path: Path) -> None:
    runner = CliRunner()
    for arguments in (
        ["--workspace", str(tmp_path), "--json", "map"],
        ["--workspace", str(tmp_path), "--json", "does-not-exist"],
    ):
        result = runner.invoke(cli, arguments)
        assert result.exit_code == 3
        assert result.stderr == ""
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["token"] == "CLI=INVALID"
        assert payload["exit_code"] == 3


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
