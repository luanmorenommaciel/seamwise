"""Workspace discovery, initialization, and stage-state inspection."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from seamwise.constants import (
    EXIT_CONFLICT,
    EXIT_INVALID,
    EXIT_OK,
    INIT_READY,
    STATUS_BLOCKED,
    STATUS_READY,
)
from seamwise.io import (
    TransactionWriter,
    UnsafeWriteTargetError,
    load_frontmatter,
    load_yaml,
    workspace_lock,
)
from seamwise.result import Diagnostic, Result
from seamwise.safety import MANAGED_WORKSPACE_DIRECTORIES, workspace_boundary_diagnostics


def resolve_workspace(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    configured = os.environ.get("SEAMWISE_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "seamwise" / "intent.md").is_file():
            return candidate
    try:
        output = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=current,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return current
    return Path(output).resolve()


def init_workspace(root: Path, *, force: bool = False, dry_run: bool = False) -> Result:
    root = root.resolve()
    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result(
            command="init",
            token="WORKSPACE=BLOCKED",
            exit_code=EXIT_CONFLICT,
            workspace=root,
            diagnostics=boundary_diagnostics,
        )
    writer = TransactionWriter(dry_run=dry_run)
    starter_documents = [
        root / "seamwise" / "intent.md",
        root / "seamwise" / "system-map.md",
    ]
    derived_starters = [
        root / "seamwise" / "evidence.jsonl",
        root / "seamwise" / "seam-map.yaml",
        root / "seamwise" / "steel-thread.md",
        root / "tasks" / "task-graph.yaml",
    ]
    collisions = [path for path in [*starter_documents, *derived_starters] if path.exists()]
    if not force and collisions:
        return Result(
            command="init",
            token="WORKSPACE=EXISTS",
            exit_code=EXIT_INVALID,
            workspace=root,
            diagnostics=[
                Diagnostic(
                    "workspace_exists",
                    "Refusing to replace any existing workspace artifact.",
                    detail={"paths": [str(path) for path in collisions]},
                )
            ],
            next_steps=["seamwise status"],
        )
    if not dry_run:
        for directory in MANAGED_WORKSPACE_DIRECTORIES:
            (root / directory).mkdir(parents=True, exist_ok=True)
    intent = """---
schema_version: 1
kind: delivery-intent
id: DI-001
title: Replace with the delivery outcome
claim: proposed
source:
  uri: human-input
  captured_at: null
  sha256: null
success: []
out_of_scope: []
---
# Delivery Intent

Describe the observable delivery outcome and the evidence that will prove it.
"""
    system_map = """---
schema_version: 1
kind: system-map
claim: proposed
components: []
external_dependencies: []
unknowns: []
---
# System Map

Record current boundaries and cite the source for every material claim.
"""
    writer.text(starter_documents[0], intent)
    writer.text(starter_documents[1], system_map)
    initial_content = {
        derived_starters[0]: "",
        derived_starters[1]: "schema_version: 1\nstatus: empty\nseams: []\n",
        derived_starters[2]: "# Steel Thread\n\nNot compiled.\n",
        derived_starters[3]: "schema_version: 1\nstatus: empty\nnodes: []\nedges: []\n",
    }
    for path, content in initial_content.items():
        if not path.exists():
            writer.text(path, content)
    with workspace_lock(root, dry_run=dry_run):
        if not force and any(path.exists() for path in writer.touched):
            return Result(
                command="init",
                token="WORKSPACE=EXISTS",
                exit_code=EXIT_INVALID,
                workspace=root,
                diagnostics=[
                    Diagnostic("workspace_race", "Workspace artifacts appeared during init.")
                ],
            )
        if force and any(path.exists() for path in writer.touched if path in derived_starters):
            return Result(
                command="init",
                token="WORKSPACE=EXISTS",
                exit_code=EXIT_INVALID,
                workspace=root,
                diagnostics=[
                    Diagnostic(
                        "workspace_race", "Derived workspace artifacts appeared during init."
                    )
                ],
            )
        try:
            writer.commit()
        except UnsafeWriteTargetError as error:
            return Result(
                command="init",
                token="WORKSPACE=BLOCKED",
                exit_code=EXIT_CONFLICT,
                workspace=root,
                diagnostics=[Diagnostic("unsafe_write_target", str(error))],
            )
    return Result(
        command="init",
        token=INIT_READY,
        exit_code=EXIT_OK,
        workspace=root,
        artifacts=writer.touched,
        next_steps=["Author evidence, then run: seamwise map --source <recipe.yaml>"],
        data={"dry_run": dry_run},
    )


def _stage_state_unlocked(root: Path) -> dict[str, Any]:
    from seamwise.engine import verify_plan, verify_seam_map
    from seamwise.taskpack import (
        _verify_task_bundle_unlocked,
        verify_check_receipt,
        verify_tier1_seals,
    )

    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return {
            "initialized": False,
            "seam_map": False,
            "delivery_plan": False,
            "reviewed": False,
            "task_graph": False,
            "task_specs": 0,
            "validated": False,
            "preflight_ready": False,
            "sealed_task_specs": 0,
            "claimed_sealed_task_specs": 0,
            "authority_gaps": [],
            "issues": [item.as_dict() for item in boundary_diagnostics],
        }
    seam_map = root / "seamwise" / "seam-map.yaml"
    plan = root / "seamwise" / "delivery-plan.yaml"
    review = root / "seamwise" / "reviews" / "delivery-plan-review.json"
    graph = root / "tasks" / "task-graph.yaml"
    issues: list[dict[str, Any]] = []
    starter_paths = [
        root / "seamwise" / "intent.md",
        root / "seamwise" / "system-map.md",
        root / "seamwise" / "evidence.jsonl",
    ]
    initialized = all(path.is_file() for path in starter_paths)
    if initialized:
        try:
            intent, _ = load_frontmatter(starter_paths[0])
            system, _ = load_frontmatter(starter_paths[1])
            initialized = (
                intent.get("kind") == "delivery-intent" and system.get("kind") == "system-map"
            )
            for line in starter_paths[2].read_text(encoding="utf-8").splitlines():
                if line.strip() and not isinstance(json.loads(line), dict):
                    raise ValueError("evidence record must be an object")
        except (OSError, ValueError):
            initialized = False
            issues.append(
                {"code": "workspace_starter_invalid", "message": "Starter documents are invalid."}
            )

    seam_ready = False
    seam_started = False
    if seam_map.is_file():
        try:
            seam_started = load_yaml(seam_map).get("status") != "empty"
        except (AttributeError, OSError, ValueError, yaml.YAMLError):
            seam_started = True
    if initialized and seam_started:
        _, diagnostics = verify_seam_map(root)
        seam_ready = not diagnostics
        if diagnostics:
            issues.extend(item.as_dict() for item in diagnostics)

    plan_ready = False
    reviewed = False
    if seam_ready and plan.is_file():
        _, diagnostics = verify_plan(root, require_review=False)
        plan_ready = not diagnostics
        if diagnostics:
            issues.extend(item.as_dict() for item in diagnostics)
    if plan_ready and review.is_file():
        _, diagnostics = verify_plan(root)
        reviewed = not diagnostics
        if diagnostics:
            issues.extend(item.as_dict() for item in diagnostics)

    graph_ready = False
    specs: list[Path] = []
    graph_started = False
    if graph.is_file():
        try:
            graph_started = load_yaml(graph).get("status") != "empty"
        except (AttributeError, OSError, ValueError, yaml.YAMLError):
            graph_started = True
    if reviewed and graph_started:
        specs, _, diagnostics = _verify_task_bundle_unlocked(root)
        graph_ready = not diagnostics
        if diagnostics:
            issues.extend(item.as_dict() for item in diagnostics)

    validated = False
    preflight_ready = False
    sealed_task_specs = 0
    claimed_sealed_task_specs = 0
    authority_gaps: list[dict[str, Any]] = []
    if graph_ready:
        validated = not verify_check_receipt(root, "validate", specs)
        preflight_ready = not verify_check_receipt(root, "preflight", specs)
        sealed_task_specs, claimed_sealed_task_specs, seal_diagnostics = verify_tier1_seals(
            root, specs
        )
        for diagnostic in seal_diagnostics:
            target = (
                authority_gaps if diagnostic.code == "tier1_verification_unavailable" else issues
            )
            target.append(diagnostic.as_dict())
    return {
        "initialized": initialized,
        "seam_map": seam_ready,
        "delivery_plan": plan_ready,
        "reviewed": reviewed,
        "task_graph": graph_ready,
        "task_specs": len(specs) if graph_ready else 0,
        "validated": validated,
        "preflight_ready": preflight_ready,
        "sealed_task_specs": sealed_task_specs,
        "claimed_sealed_task_specs": claimed_sealed_task_specs,
        "authority_gaps": authority_gaps,
        "issues": issues,
    }


def stage_state(root: Path) -> dict[str, Any]:
    if workspace_boundary_diagnostics(root):
        return _stage_state_unlocked(root)
    with workspace_lock(root):
        return _stage_state_unlocked(root)


def next_steps_for_state(state: dict[str, Any]) -> list[str]:
    """Return the next authority-bounded action for one coherent state snapshot."""

    if state["issues"]:
        return ["Resolve the reported integrity issue before continuing."]
    elif not state["initialized"]:
        return ["seamwise init"]
    elif not state["seam_map"]:
        return ["seamwise map --source <recipe.yaml>"]
    elif not state["delivery_plan"]:
        return ["seamwise plan"]
    elif not state["reviewed"]:
        return ["seamwise review --accept --reviewer <name> --reason <reason>"]
    elif not state["task_graph"]:
        return ["seamwise compile"]
    elif not state["validated"]:
        return ["seamwise tasks validate"]
    elif not state["preflight_ready"]:
        return ["seamwise tasks preflight --acknowledge-eval-execution"]
    elif state["claimed_sealed_task_specs"] > state["sealed_task_specs"]:
        return [
            "Restore or configure the Task-Spec signing key, then rerun seamwise status; "
            "until Tier 1 verifies, dispatch only under human supervision."
        ]
    elif state["sealed_task_specs"] == state["task_specs"] and state["task_specs"] > 0:
        return ["Tier-1-sealed Task-Specs are ready for authority-bounded dispatch."]
    return ["Review drafts; seal only with explicit dispatch authority."]


def status_result(root: Path) -> Result:
    state = stage_state(root)
    next_steps = next_steps_for_state(state)
    return Result(
        command="status",
        token=STATUS_BLOCKED if state["issues"] else STATUS_READY,
        exit_code=EXIT_CONFLICT if state["issues"] else EXIT_OK,
        workspace=root,
        diagnostics=[
            Diagnostic(
                str(item.get("code", "workspace_integrity_error")),
                str(item.get("message", "Workspace integrity check failed.")),
                item.get("artifact"),
                item.get("detail", {}),
            )
            for item in state["issues"]
        ],
        next_steps=next_steps,
        data=state,
    )
