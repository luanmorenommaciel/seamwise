from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import seamwise.installer as installer_module
from seamwise.installer import install, uninstall
from seamwise.io import private_state_path
from seamwise.taskpack import CANONICAL_SKILLS, SEAMWISE_SKILLS


def receipt_path(target: Path, host: str) -> Path:
    return private_state_path(target, "install", f"{host}.json")


def test_install_reinstall_and_receipt_owned_uninstall(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    installed = install(tmp_path, host="all", scope="project", target=target, dry_run=False)
    assert installed.token == "INSTALL=OK"
    for host_dir in (target / ".agents/skills", target / ".claude/skills"):
        assert {item.name for item in host_dir.iterdir()} == set(SEAMWISE_SKILLS)
    assert receipt_path(target, "codex").is_file()
    assert receipt_path(target, "claude").is_file()

    reinstalled = install(tmp_path, host="all", scope="project", target=target, dry_run=False)
    assert reinstalled.token == "INSTALL=OK"

    removed = uninstall(tmp_path, host="all", scope="project", target=target, dry_run=False)
    assert removed.token == "UNINSTALL=OK"
    assert not (target / ".agents/skills/seamwise").exists()
    assert not (target / ".claude/skills/seamwise").exists()


def test_installer_refuses_unowned_and_modified_destinations(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    unowned = target / ".agents/skills/seamwise"
    unowned.mkdir(parents=True)
    (unowned / "mine.txt").write_text("mine", encoding="utf-8")
    blocked = install(tmp_path, host="codex", scope="project", target=target, dry_run=False)
    assert blocked.token == "INSTALL=BLOCKED"
    assert (unowned / "mine.txt").read_text(encoding="utf-8") == "mine"

    clean_target = tmp_path / "clean"
    assert install(tmp_path, host="codex", scope="project", target=clean_target, dry_run=False).ok
    modified = clean_target / ".agents/skills/seamwise/SKILL.md"
    modified.write_text(modified.read_text(encoding="utf-8") + "\nlocal\n", encoding="utf-8")
    result = uninstall(tmp_path, host="codex", scope="project", target=clean_target, dry_run=False)
    assert result.token == "UNINSTALL=BLOCKED"
    assert modified.exists()


def test_install_dry_run_has_no_side_effects(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    result = install(tmp_path, host="all", scope="project", target=target, dry_run=True)
    assert result.token == "INSTALL=OK"
    assert result.data["dry_run"] is True
    assert not target.exists()


def test_direct_task_spec_skill_is_explicit_opt_in(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    result = install(
        tmp_path,
        host="codex",
        scope="project",
        target=target,
        dry_run=False,
        include_task_spec=True,
    )
    assert result.ok
    installed = {item.name for item in (target / ".agents/skills").iterdir()}
    assert installed == set(CANONICAL_SKILLS)

    reinstalled = install(
        tmp_path,
        host="codex",
        scope="project",
        target=target,
        dry_run=False,
    )
    assert reinstalled.ok
    receipt = json.loads(receipt_path(target, "codex").read_text())
    assert {item["skill"] for item in receipt["entries"]} == set(CANONICAL_SKILLS)
    assert uninstall(tmp_path, host="codex", scope="project", target=target, dry_run=False).ok
    assert not (target / ".agents/skills/task-spec").exists()


def test_unrelated_optional_task_spec_symlink_does_not_block_default_install(
    tmp_path: Path,
) -> None:
    target = tmp_path / "consumer"
    outside = tmp_path / "outside-task-spec"
    outside.mkdir()
    parent = target / ".agents/skills"
    parent.mkdir(parents=True)
    optional = parent / "task-spec"
    optional.symlink_to(outside, target_is_directory=True)

    installed = install(tmp_path, host="codex", scope="project", target=target, dry_run=False)
    assert installed.ok
    assert {item.name for item in parent.iterdir() if not item.is_symlink()} == set(SEAMWISE_SKILLS)
    assert optional.is_symlink()
    assert uninstall(tmp_path, host="codex", scope="project", target=target, dry_run=False).ok
    assert optional.is_symlink()


def test_installer_rejects_tampered_receipt_target(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    assert install(tmp_path, host="codex", scope="project", target=target, dry_run=False).ok
    receipt_file = receipt_path(target, "codex")
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    receipt["entries"][0]["target"] = str(victim)
    receipt_file.write_text(json.dumps(receipt), encoding="utf-8")

    blocked_install = install(tmp_path, host="codex", scope="project", target=target, dry_run=False)
    blocked_uninstall = uninstall(
        tmp_path, host="codex", scope="project", target=target, dry_run=False
    )
    assert blocked_install.token == "INSTALL=BLOCKED"
    assert blocked_uninstall.token == "UNINSTALL=BLOCKED"
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_install_rolls_back_if_staging_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "consumer"
    original = installer_module.shutil.copytree

    def flaky_copytree(*args, **kwargs):  # type: ignore[no-untyped-def]
        if Path(args[0]).name == "to-seam-map":
            raise OSError("injected staging failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(installer_module.shutil, "copytree", flaky_copytree)
    result = install(tmp_path, host="codex", scope="project", target=target, dry_run=False)
    assert result.token == "INSTALL=ROLLED_BACK"
    assert not (target / ".agents/skills/seamwise").exists()
    assert not receipt_path(target, "codex").exists()


def test_install_rolls_back_files_and_receipts_if_receipt_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "consumer"
    original = installer_module.Writer.json

    def flaky_json(self, path, value):  # type: ignore[no-untyped-def]
        if Path(path).name == "claude.json":
            raise OSError("injected receipt failure")
        return original(self, path, value)

    monkeypatch.setattr(installer_module.Writer, "json", flaky_json)
    result = install(tmp_path, host="all", scope="project", target=target, dry_run=False)
    assert result.token == "INSTALL=ROLLED_BACK"
    assert not (target / ".agents/skills/seamwise").exists()
    assert not (target / ".claude/skills/seamwise").exists()
    assert not receipt_path(target, "codex").exists()
    assert not receipt_path(target, "claude").exists()


@pytest.mark.parametrize(
    ("host", "redirect"),
    (
        ("codex", ".agents"),
        ("codex", ".agents/skills"),
        ("claude", ".claude"),
        ("claude", ".claude/skills"),
    ),
)
def test_project_install_refuses_symlinked_host_ancestors(
    tmp_path: Path, host: str, redirect: str
) -> None:
    target = tmp_path / "consumer"
    outside = tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    link = target / redirect
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)

    result = install(tmp_path, host=host, scope="project", target=target, dry_run=False)
    assert result.token == "INSTALL=BLOCKED"
    assert result.exit_code == 4
    assert any(item.code == "unsafe_install_path" for item in result.diagnostics)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    ("host", "occupied"),
    (
        ("codex", ".agents"),
        ("codex", ".agents/skills"),
        ("claude", ".claude"),
        ("claude", ".claude/skills"),
    ),
)
def test_project_install_refuses_regular_file_host_ancestors(
    tmp_path: Path, host: str, occupied: str
) -> None:
    target = tmp_path / "consumer"
    target.mkdir()
    path = target / occupied
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a directory", encoding="utf-8")

    result = install(tmp_path, host=host, scope="project", target=target, dry_run=False)
    assert result.token == "INSTALL=BLOCKED"
    assert result.exit_code == 4
    assert any(item.code == "unsafe_install_path" for item in result.diagnostics)


def test_project_install_refuses_regular_file_target(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    target.write_text("not a directory", encoding="utf-8")
    result = install(tmp_path, host="codex", scope="project", target=target, dry_run=False)
    assert result.token == "INSTALL=BLOCKED"
    assert any(item.code == "unsafe_install_path" for item in result.diagnostics)


def test_project_install_refuses_symlinked_private_state_ancestor(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    target.mkdir()
    state_home = Path(os.environ["SEAMWISE_STATE_HOME"])
    outside = tmp_path / "outside-state"
    state_home.mkdir(parents=True)
    outside.mkdir()
    (state_home / "workspaces").symlink_to(outside, target_is_directory=True)

    result = install(tmp_path, host="codex", scope="project", target=target, dry_run=False)
    assert result.token == "INSTALL=BLOCKED"
    assert any(item.code == "unsafe_install_receipt_path" for item in result.diagnostics)
    assert list(outside.iterdir()) == []
