"""Receipt-owned, transactional skill installation for Codex and Claude Code."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import shutil
import stat
import tempfile
import uuid
from pathlib import Path
from typing import Any

from seamwise.constants import (
    EXIT_CONFLICT,
    EXIT_INVALID,
    EXIT_OK,
    INSTALL_OK,
    UNINSTALL_OK,
    VERSION,
)
from seamwise.contracts import validate_contract
from seamwise.io import Writer, load_json, private_state_path, sha256_object, workspace_lock
from seamwise.result import Diagnostic, Result
from seamwise.safety import path_boundary_diagnostics
from seamwise.taskpack import CANONICAL_SKILLS, SEAMWISE_SKILLS, skills_root

HOSTS = ("codex", "claude")


def _hosts(value: str) -> tuple[str, ...]:
    return HOSTS if value == "all" else (value,)


def _base(root: Path, scope: str, target: Path | None) -> Path:
    if target is not None:
        return Path(os.path.abspath(target.expanduser()))
    return Path(os.path.abspath(root)) if scope == "project" else Path.home().resolve()


def _skill_parent(base: Path, host: str) -> Path:
    return base / (".agents/skills" if host == "codex" else ".claude/skills")


def _receipt_path(base: Path, host: str, scope: str) -> Path:
    directory = (
        private_state_path(base, "install") if scope == "project" else base / ".seamwise/receipts"
    )
    return directory / f"{host}.json"


def _install_boundary_diagnostics(
    base: Path,
    host: str,
    scope: str,
    *,
    selected_skills: tuple[str, ...] | None = None,
) -> list[Diagnostic]:
    if host not in (*HOSTS, "all") or scope not in ("project", "user"):
        return []
    targets: list[Path] = []
    for current_host in _hosts(host):
        parent = _skill_parent(base, current_host)
        targets.append(parent)
        if selected_skills is not None:
            targets.extend(parent / skill for skill in selected_skills)
    diagnostics = path_boundary_diagnostics(base, targets, code="unsafe_install_path")
    if base.exists() and not base.is_dir() and not base.is_symlink():
        diagnostics.append(
            Diagnostic(
                "unsafe_install_path",
                "The installation base is not a directory.",
                str(base),
            )
        )
    for current_host in _hosts(host):
        parent = _skill_parent(base, current_host)
        if parent.exists() and not parent.is_dir() and not parent.is_symlink():
            diagnostics.append(
                Diagnostic(
                    "unsafe_install_path",
                    "The host skill directory slot is occupied by a non-directory.",
                    str(parent),
                )
            )
    if base.is_symlink() or (base.exists() and not base.is_dir()):
        return diagnostics
    for current_host in _hosts(host):
        receipt = _receipt_path(base, current_host, scope)
        if scope == "user":
            diagnostics.extend(
                path_boundary_diagnostics(base, [receipt], code="unsafe_install_receipt_path")
            )
        else:
            private_anchor = private_state_path(base)
            diagnostics.extend(
                path_boundary_diagnostics(
                    private_anchor.parent,
                    [receipt],
                    code="unsafe_install_receipt_path",
                )
            )
    return diagnostics


def _tree_inventory(root: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == ".DS_Store":
            continue
        relative = str(path.relative_to(root))
        mode = format(stat.S_IMODE(path.lstat().st_mode), "04o")
        if path.is_symlink():
            inventory[relative] = {"type": "symlink", "mode": mode, "target": os.readlink(path)}
        elif path.is_dir():
            inventory[relative] = {"type": "directory", "mode": mode}
        elif path.is_file():
            inventory[relative] = {
                "type": "file",
                "mode": mode,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        else:
            inventory[relative] = {"type": "special", "mode": mode}
    return inventory


def _tree_digest(root: Path) -> str:
    return sha256_object(_tree_inventory(root))


def _validated_receipt(
    path: Path, *, base: Path, host: str, scope: str
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    if not path.is_file():
        return None, []
    try:
        value = load_json(path)
    except (OSError, ValueError) as error:
        return None, [
            Diagnostic(
                "install_receipt_invalid", f"Cannot read install receipt: {error}", str(path)
            )
        ]
    if not isinstance(value, dict):
        return None, [
            Diagnostic("install_receipt_invalid", "Install receipt is not an object.", str(path))
        ]
    errors = validate_contract("install-receipt", value)
    diagnostics = [Diagnostic("install_receipt_invalid", message, str(path)) for message in errors]
    expected_base = str(base)
    if value.get("host") != host:
        diagnostics.append(
            Diagnostic("install_receipt_host_mismatch", "Receipt host does not match.", str(path))
        )
    if value.get("scope") != scope:
        diagnostics.append(
            Diagnostic("install_receipt_scope_mismatch", "Receipt scope does not match.", str(path))
        )
    if value.get("base") != expected_base:
        diagnostics.append(
            Diagnostic("install_receipt_base_mismatch", "Receipt base does not match.", str(path))
        )
    seen_skills: set[str] = set()
    seen_targets: set[str] = set()
    entries = value.get("entries", [])
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            skill = entry.get("skill")
            target = entry.get("target")
            if skill not in CANONICAL_SKILLS:
                diagnostics.append(
                    Diagnostic(
                        "install_receipt_unknown_skill",
                        f"Receipt names an unsupported skill: {skill!r}",
                        str(path),
                    )
                )
                continue
            expected_target = Path(os.path.abspath(_skill_parent(base, host) / skill))
            try:
                actual_target = Path(os.path.abspath(Path(str(target)).expanduser()))
            except (OSError, RuntimeError, ValueError):
                actual_target = Path("/")
            if actual_target != expected_target:
                diagnostics.append(
                    Diagnostic(
                        "install_receipt_target_mismatch",
                        f"Receipt target escapes the owned skill location: {target!r}",
                        str(path),
                    )
                )
            diagnostics.extend(
                path_boundary_diagnostics(
                    base,
                    [expected_target],
                    code="unsafe_install_path",
                )
            )
            if skill in seen_skills or str(target) in seen_targets:
                diagnostics.append(
                    Diagnostic(
                        "install_receipt_duplicate_entry",
                        f"Receipt repeats a skill or target: {skill!r}",
                        str(path),
                    )
                )
            seen_skills.add(skill)
            seen_targets.add(str(target))
    return (None if diagnostics else value), diagnostics


def install(
    root: Path,
    *,
    host: str,
    scope: str,
    target: Path | None,
    dry_run: bool,
    include_task_spec: bool = False,
) -> Result:
    base = _base(root, scope, target)
    selected_skills = CANONICAL_SKILLS if include_task_spec else SEAMWISE_SKILLS
    boundary_diagnostics = _install_boundary_diagnostics(
        base, host, scope, selected_skills=selected_skills
    )
    if boundary_diagnostics:
        return Result(
            "install",
            "INSTALL=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=boundary_diagnostics,
        )
    with workspace_lock(base, dry_run=dry_run):
        return _install_unlocked(
            root,
            host=host,
            scope=scope,
            target=target,
            dry_run=dry_run,
            include_task_spec=include_task_spec,
        )


def _install_unlocked(
    root: Path,
    *,
    host: str,
    scope: str,
    target: Path | None,
    dry_run: bool,
    include_task_spec: bool = False,
) -> Result:
    if host not in (*HOSTS, "all") or scope not in ("project", "user"):
        return Result(
            "install",
            "INSTALL=INVALID",
            EXIT_INVALID,
            root,
            diagnostics=[Diagnostic("invalid_install_target", "Host or scope is invalid.")],
        )
    base = _base(root, scope, target)
    selected_skills = CANONICAL_SKILLS if include_task_spec else SEAMWISE_SKILLS
    boundary_diagnostics = _install_boundary_diagnostics(
        base, host, scope, selected_skills=selected_skills
    )
    if boundary_diagnostics:
        return Result(
            "install",
            "INSTALL=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=boundary_diagnostics,
        )
    source_root = skills_root()
    plan: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    receipts_by_host: dict[str, dict[str, Any] | None] = {}
    for current_host in _hosts(host):
        receipt_path = _receipt_path(base, current_host, scope)
        receipt, receipt_diagnostics = _validated_receipt(
            receipt_path, base=base, host=current_host, scope=scope
        )
        diagnostics.extend(receipt_diagnostics)
        receipts_by_host[current_host] = receipt
        owned = {item["target"]: item for item in receipt.get("entries", [])} if receipt else {}
        parent = _skill_parent(base, current_host)
        for skill in selected_skills:
            source = source_root / skill
            planned_destination = parent / skill
            if not source.is_dir():
                diagnostics.append(
                    Diagnostic(
                        "skill_source_missing", f"Bundled skill is missing: {skill}", str(source)
                    )
                )
                continue
            previous = owned.get(str(planned_destination))
            if planned_destination.exists() and previous is None:
                diagnostics.append(
                    Diagnostic(
                        "unowned_destination",
                        f"Refusing to replace unowned skill directory: {planned_destination}",
                        str(planned_destination),
                    )
                )
                continue
            if planned_destination.exists() and previous is not None:
                actual = _tree_digest(planned_destination)
                if actual != previous["sha256"]:
                    diagnostics.append(
                        Diagnostic(
                            "installed_skill_modified",
                            f"Refusing to replace locally modified skill: {planned_destination}",
                            str(planned_destination),
                            {"expected_sha256": previous["sha256"], "actual_sha256": actual},
                        )
                    )
                    continue
            plan.append(
                {
                    "host": current_host,
                    "skill": skill,
                    "source": source,
                    "target": planned_destination,
                    "sha256": _tree_digest(source),
                    "files": len(_tree_inventory(source)),
                }
            )
    if diagnostics:
        return Result(
            "install",
            "INSTALL=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=diagnostics,
            next_steps=["Move the unowned directory or restore receipt-owned files, then retry."],
        )
    receipt_paths = [_receipt_path(base, item, scope) for item in _hosts(host)]
    if dry_run:
        return Result(
            "install",
            INSTALL_OK,
            EXIT_OK,
            root,
            artifacts=[*[item["target"] for item in plan], *receipt_paths],
            next_steps=["Rerun this exact command without --dry-run; preserve every option."],
            data={"dry_run": True, "changes": _serializable_plan(plan)},
        )
    installed: list[tuple[Path, Path | None]] = []
    staged: list[Path] = []
    receipt_snapshots: dict[Path, str | None] = {}
    writer = Writer()
    try:
        for item in plan:
            target_path: Path = item["target"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            stage_parent = Path(tempfile.mkdtemp(prefix=".seamwise-stage-", dir=target_path.parent))
            staged.append(stage_parent)
            staged_skill = stage_parent / target_path.name
            shutil.copytree(item["source"], staged_skill, copy_function=shutil.copy2)
            if _tree_digest(staged_skill) != item["sha256"]:
                raise RuntimeError(f"staged hash mismatch for {target_path}")
            backup: Path | None = None
            if target_path.exists():
                backup = (
                    target_path.parent / f".{target_path.name}.seamwise-backup-{uuid.uuid4().hex}"
                )
                os.replace(target_path, backup)
            os.replace(staged_skill, target_path)
            installed.append((target_path, backup))
        for current_host in _hosts(host):
            entries = [item for item in plan if item["host"] == current_host]
            previous_receipt = receipts_by_host[current_host]
            previous_entries = previous_receipt.get("entries", []) if previous_receipt else []
            updated_skills = {item["skill"] for item in entries}
            preserved_entries = [
                item for item in previous_entries if item["skill"] not in updated_skills
            ]
            receipt = {
                "schema_version": 1,
                "seamwise_version": VERSION,
                "host": current_host,
                "scope": scope,
                "base": str(base),
                "installed_at": dt.datetime.now(dt.UTC).isoformat(),
                "entries": [
                    {
                        "skill": item["skill"],
                        "target": str(item["target"]),
                        "sha256": item["sha256"],
                        "files": item["files"],
                    }
                    for item in entries
                ]
                + preserved_entries,
            }
            receipt_errors = validate_contract("install-receipt", receipt)
            if receipt_errors:
                raise RuntimeError("invalid install receipt: " + "; ".join(receipt_errors))
            receipt_path = _receipt_path(base, current_host, scope)
            receipt_snapshots[receipt_path] = (
                receipt_path.read_text(encoding="utf-8") if receipt_path.is_file() else None
            )
            writer.json(receipt_path, receipt)
    except Exception as error:
        for receipt_path, snapshot in receipt_snapshots.items():
            if snapshot is None:
                if receipt_path.exists():
                    receipt_path.unlink()
            else:
                Writer().text(receipt_path, snapshot)
        for destination, backup in reversed(installed):
            if destination.exists():
                shutil.rmtree(destination)
            if backup is not None and backup.exists():
                os.replace(backup, destination)
        for stage in staged:
            if stage.exists():
                shutil.rmtree(stage)
        return Result(
            "install",
            "INSTALL=ROLLED_BACK",
            EXIT_CONFLICT,
            root,
            diagnostics=[Diagnostic("install_transaction_failed", str(error))],
        )
    for _, backup in installed:
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
    for stage in staged:
        if stage.exists():
            shutil.rmtree(stage)
    return Result(
        "install",
        INSTALL_OK,
        EXIT_OK,
        root,
        artifacts=[*[item["target"] for item in plan], *writer.touched],
        next_steps=_host_restart_steps(host),
        data={"dry_run": False, "changes": _serializable_plan(plan)},
    )


def _serializable_plan(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "host": item["host"],
            "skill": item["skill"],
            "source": str(item["source"]),
            "target": str(item["target"]),
            "sha256": item["sha256"],
            "files": item["files"],
        }
        for item in plan
    ]


def _host_restart_steps(host: str) -> list[str]:
    steps: list[str] = []
    if host in ("codex", "all"):
        steps.append("Start a new Codex session, then invoke $seamwise.")
    if host in ("claude", "all"):
        steps.append("Start a new Claude Code session, then invoke /seamwise.")
    return steps


def verify_installation(
    root: Path, *, host: str, scope: str = "project", target: Path | None = None
) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    base = _base(root, scope, target)
    checks: list[dict[str, Any]] = []
    diagnostics = _install_boundary_diagnostics(base, host, scope)
    if diagnostics:
        return checks, diagnostics
    with workspace_lock(base):
        for current_host in _hosts(host):
            receipt_path = _receipt_path(base, current_host, scope)
            receipt, receipt_diagnostics = _validated_receipt(
                receipt_path, base=base, host=current_host, scope=scope
            )
            diagnostics.extend(receipt_diagnostics)
            if receipt is None:
                if not receipt_diagnostics:
                    diagnostics.append(
                        Diagnostic(
                            "install_receipt_missing",
                            f"No receipt-owned {current_host} installation exists.",
                            str(receipt_path),
                        )
                    )
                checks.append(
                    {
                        "name": f"{current_host}_installation",
                        "ok": False,
                        "receipt": str(receipt_path),
                    }
                )
                continue
            host_ok = True
            for entry in receipt["entries"]:
                destination = Path(entry["target"])
                source = skills_root() / entry["skill"]
                actual = _tree_digest(destination) if destination.is_dir() else None
                source_digest = _tree_digest(source) if source.is_dir() else None
                ok = actual == entry["sha256"] == source_digest
                host_ok = host_ok and ok
                checks.append(
                    {
                        "name": f"{current_host}:{entry['skill']}",
                        "ok": ok,
                        "target": str(destination),
                        "expected_sha256": entry["sha256"],
                        "actual_sha256": actual,
                        "source_sha256": source_digest,
                    }
                )
                if not ok:
                    diagnostics.append(
                        Diagnostic(
                            "installed_skill_hash_mismatch",
                            f"Installed {current_host} skill differs: {entry['skill']}.",
                            str(destination),
                        )
                    )
            checks.append(
                {
                    "name": f"{current_host}_installation",
                    "ok": host_ok,
                    "receipt": str(receipt_path),
                }
            )
    return checks, diagnostics


def uninstall(
    root: Path,
    *,
    host: str,
    scope: str,
    target: Path | None,
    dry_run: bool,
) -> Result:
    base = _base(root, scope, target)
    boundary_diagnostics = _install_boundary_diagnostics(base, host, scope)
    if boundary_diagnostics:
        return Result(
            "uninstall",
            "UNINSTALL=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=boundary_diagnostics,
        )
    with workspace_lock(base, dry_run=dry_run):
        return _uninstall_unlocked(
            root,
            host=host,
            scope=scope,
            target=target,
            dry_run=dry_run,
        )


def _uninstall_unlocked(
    root: Path,
    *,
    host: str,
    scope: str,
    target: Path | None,
    dry_run: bool,
) -> Result:
    base = _base(root, scope, target)
    boundary_diagnostics = _install_boundary_diagnostics(base, host, scope)
    if boundary_diagnostics:
        return Result(
            "uninstall",
            "UNINSTALL=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=boundary_diagnostics,
        )
    entries: list[dict[str, Any]] = []
    receipts: list[Path] = []
    diagnostics: list[Diagnostic] = []
    for current_host in _hosts(host):
        receipt_path = _receipt_path(base, current_host, scope)
        receipt, receipt_diagnostics = _validated_receipt(
            receipt_path, base=base, host=current_host, scope=scope
        )
        diagnostics.extend(receipt_diagnostics)
        if receipt is None:
            if not receipt_diagnostics:
                diagnostics.append(
                    Diagnostic(
                        "receipt_missing",
                        f"No Seamwise receipt exists for {current_host}.",
                        str(receipt_path),
                    )
                )
            continue
        receipts.append(receipt_path)
        for entry in receipt["entries"]:
            destination = Path(entry["target"])
            if not destination.is_dir():
                diagnostics.append(
                    Diagnostic(
                        "installed_skill_missing", f"Receipt target is missing: {destination}"
                    )
                )
            elif _tree_digest(destination) != entry["sha256"]:
                diagnostics.append(
                    Diagnostic(
                        "installed_skill_modified",
                        f"Refusing to remove locally modified skill: {destination}",
                        str(destination),
                    )
                )
            entries.append({**entry, "target_path": destination})
    if diagnostics:
        return Result(
            "uninstall",
            "UNINSTALL=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=diagnostics,
            next_steps=[
                "Restore receipt-owned contents or remove the modified directory manually."
            ],
        )
    targets = [item["target_path"] for item in entries]
    if dry_run:
        return Result(
            "uninstall",
            UNINSTALL_OK,
            EXIT_OK,
            root,
            artifacts=[*targets, *receipts],
            data={"dry_run": True, "remove": [str(path) for path in targets]},
        )
    moved: list[tuple[Path, Path]] = []
    receipt_snapshots = {
        receipt_file: receipt_file.read_text(encoding="utf-8") for receipt_file in receipts
    }
    try:
        for destination in targets:
            backup = (
                destination.parent / f".{destination.name}.seamwise-uninstall-{uuid.uuid4().hex}"
            )
            os.replace(destination, backup)
            moved.append((destination, backup))
        for receipt_file in receipts:
            receipt_file.unlink()
    except Exception as error:
        for receipt_file, content in receipt_snapshots.items():
            if not receipt_file.exists():
                Writer().text(receipt_file, content)
        for destination, backup in reversed(moved):
            if backup.exists():
                os.replace(backup, destination)
        return Result(
            "uninstall",
            "UNINSTALL=ROLLED_BACK",
            EXIT_CONFLICT,
            root,
            diagnostics=[Diagnostic("uninstall_transaction_failed", str(error))],
        )
    for _, backup in moved:
        shutil.rmtree(backup)
    return Result(
        "uninstall",
        UNINSTALL_OK,
        EXIT_OK,
        root,
        artifacts=[*targets, *receipts],
        data={"dry_run": False, "removed": [str(path) for path in targets]},
    )
