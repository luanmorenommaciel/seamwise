"""TaskPlan and lineage compilation plus lineage inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from seamwise.constants import (
    EXIT_CONFLICT,
    EXIT_INVALID,
    EXIT_NEEDS_INPUT,
    EXIT_OK,
    GRAPH_BLOCKED,
    GRAPH_READY,
    GRAPH_UNPROVABLE,
)
from seamwise.contracts import validate_contract
from seamwise.engine.graph import _graph_projection, _task_records
from seamwise.engine.planning import verify_plan
from seamwise.engine.support import _diag
from seamwise.io import (
    TransactionWriter,
    UnsafeWriteTargetError,
    load_json,
    sha256_file,
    workspace_lock,
)
from seamwise.result import Diagnostic, Result
from seamwise.safety import workspace_boundary_diagnostics
from seamwise.taskspec_adapter import (
    TASK_PLAN_LINEAGE_PATH,
    TASK_PLAN_PATH,
    build_task_plan,
    build_task_plan_lineage,
    task_plan_digest,
)


def derive_task_bundle(
    root: Path, plan: dict[str, Any]
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[Diagnostic],
]:
    """Deterministically rebuild Seamwise-owned topology before materialization."""

    plan_sha = sha256_file(root / "seamwise" / "delivery-plan.yaml")
    records = _task_records(root, plan)
    graph, diagnostics = _graph_projection(records, plan, plan_sha)
    if diagnostics or graph["status"] != GRAPH_READY:
        return records, graph, diagnostics
    projection_errors = validate_contract("task-graph", graph)
    if projection_errors:
        return records, graph, [_diag("projection_schema", item) for item in projection_errors]
    return records, graph, []


def _task_lineage(
    root: Path,
    records: list[dict[str, Any]],
    task_plan: dict[str, Any],
) -> dict[str, Any]:
    return build_task_plan_lineage(root, records, task_plan)


def compile_graph(
    root: Path,
    *,
    dry_run: bool = False,
    command: str = "compile",
) -> Result:
    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result(command, GRAPH_BLOCKED, EXIT_CONFLICT, root, diagnostics=boundary_diagnostics)
    plan, diagnostics = verify_plan(root)
    if plan is None:
        missing_authority = {"plan_missing", "plan_not_ready", "review_missing"}
        return Result(
            command,
            GRAPH_BLOCKED,
            EXIT_NEEDS_INPUT
            if diagnostics and all(item.code in missing_authority for item in diagnostics)
            else EXIT_CONFLICT,
            root,
            diagnostics=diagnostics,
            next_steps=[
                "seamwise plan",
                "seamwise review --accept --reviewer <name> --reason <reason>",
            ],
        )
    plan_path = root / "seamwise" / "delivery-plan.yaml"
    plan_sha = sha256_file(plan_path)
    records, graph, graph_diagnostics = derive_task_bundle(root, plan)
    token = graph["status"]
    exit_code = EXIT_OK if token == GRAPH_READY else EXIT_CONFLICT
    if token != GRAPH_READY:
        return Result(
            command,
            token,
            exit_code,
            root,
            diagnostics=graph_diagnostics,
            next_steps=["Resolve graph diagnostics, then rerun compile."],
            data={"tasks": len(records), "dry_run": dry_run, "graph": graph},
        )
    if graph_diagnostics:
        return Result(
            command,
            GRAPH_UNPROVABLE,
            EXIT_INVALID,
            root,
            diagnostics=graph_diagnostics,
        )
    try:
        task_plan = build_task_plan(root, plan, records)
        lineage = _task_lineage(root, records, task_plan)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        return Result(
            command,
            GRAPH_UNPROVABLE,
            EXIT_INVALID,
            root,
            diagnostics=[_diag("task_plan_projection_failed", str(error))],
        )
    lineage_errors = validate_contract("task-lineage", lineage)
    if lineage_errors:
        return Result(
            command,
            GRAPH_UNPROVABLE,
            EXIT_INVALID,
            root,
            diagnostics=[_diag("projection_schema", item) for item in lineage_errors],
        )
    writer = TransactionWriter(dry_run=dry_run)
    with workspace_lock(root, dry_run=dry_run):
        locked_plan, locked_diagnostics = verify_plan(root)
        if locked_plan is None or sha256_file(plan_path) != plan_sha:
            return Result(
                command,
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=locked_diagnostics
                or [_diag("plan_changed", "Delivery plan changed during compilation.")],
            )
        writer.json(root / TASK_PLAN_PATH, task_plan)
        writer.json(root / TASK_PLAN_LINEAGE_PATH, lineage)
        try:
            writer.commit()
        except UnsafeWriteTargetError as error:
            return Result(
                command,
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=[_diag("unsafe_write_target", str(error))],
            )
    return Result(
        command,
        token,
        exit_code,
        root,
        artifacts=writer.touched,
        diagnostics=graph_diagnostics,
        next_steps=[
            "Pass seamwise/task-plan.json and seamwise/task-plan-lineage.json to the composition coordinator."
        ]
        if token == GRAPH_READY
        else ["Resolve graph diagnostics, then rerun compile."],
        data={
            "tasks": len(records),
            "dry_run": dry_run,
            "task_plan_contract": "TaskPlan/v1",
            "task_plan_digest": task_plan_digest(task_plan),
            "task_plan_lineage_contract": "SeamwiseTaskPlanLineage/v1",
            "dispatch_authorized": False,
            "graph": graph,
        },
    )


def inspect_lineage(root: Path, task_id: str | None = None) -> Result:
    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result(
            "inspect",
            GRAPH_BLOCKED,
            EXIT_CONFLICT,
            root,
            diagnostics=boundary_diagnostics,
        )
    with workspace_lock(root):
        path = root / TASK_PLAN_LINEAGE_PATH
        if not path.is_file():
            return Result(
                "inspect",
                GRAPH_BLOCKED,
                EXIT_NEEDS_INPUT,
                root,
                diagnostics=[_diag("lineage_missing", "Compile a task graph first.", path)],
                next_steps=["seamwise compile"],
            )
        try:
            lineage = load_json(path)
        except (OSError, ValueError) as error:
            return Result(
                "inspect",
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=[_diag("task_lineage_invalid", str(error), path)],
            )
        errors = validate_contract("task-lineage", lineage)
        if errors:
            return Result(
                "inspect",
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=[_diag("task_lineage_schema", item, path) for item in errors],
            )
        if task_id is not None:
            task = lineage["units"].get(task_id)
            if task is None:
                return Result(
                    "inspect",
                    GRAPH_UNPROVABLE,
                    EXIT_INVALID,
                    root,
                    diagnostics=[_diag("unknown_task", f"No lineage for {task_id}.")],
                )
            data = {"task_id": task_id, **task}
        else:
            data = lineage
        return Result("inspect", "LINEAGE=READY", EXIT_OK, root, artifacts=[path], data=data)
