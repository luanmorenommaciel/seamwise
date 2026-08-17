"""Seamwise command-line interface."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn, cast

import click
from rich.console import Console

from seamwise.constants import (
    EXIT_INVALID,
    EXIT_NEEDS_INPUT,
    EXIT_OK,
    GRAPH_BLOCKED,
    GRAPH_READY,
    PLAN_NEEDS_REVIEW,
    VERSION,
)
from seamwise.contracts import schema_path, validate_contract
from seamwise.doctor import doctor as run_doctor
from seamwise.engine import (
    accept_plan,
    build_plan,
    compile_graph,
    derive_task_bundle,
    inspect_lineage,
    map_recipe,
    render_graph_mermaid,
    verify_plan,
)
from seamwise.installer import install as run_install
from seamwise.installer import uninstall as run_uninstall
from seamwise.io import (
    load_yaml,
    sha256_file,
    workspace_lock,
)
from seamwise.reporting import agent_context as build_agent_context
from seamwise.reporting import build_report
from seamwise.result import Diagnostic, Result
from seamwise.workspace import init_workspace, resolve_workspace, stage_state, status_result


class State(dict[str, Any]):
    @property
    def workspace(self) -> Path:
        return cast(Path, self["workspace"])

    @property
    def json_mode(self) -> bool:
        return bool(self["json_mode"])

    @property
    def dry_run(self) -> bool:
        return bool(self["dry_run"])


pass_state = click.make_pass_decorator(State)


class EnvelopeGroup(click.Group):
    """Keep parser and runtime failures inside the versioned machine contract."""

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        arguments = list(args) if args is not None else sys.argv[1:]
        json_mode = "--json" in arguments
        workspace: Path | None = None
        if "--workspace" in arguments:
            index = arguments.index("--workspace")
            if index + 1 < len(arguments):
                workspace = Path(arguments[index + 1])
        try:
            result = super().main(
                args=arguments,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except click.ClickException as error:
            exit_code = EXIT_INVALID
            if json_mode:
                payload = Result(
                    "cli",
                    "CLI=INVALID",
                    exit_code,
                    resolve_workspace(workspace),
                    diagnostics=[Diagnostic("usage_error", error.format_message())],
                ).as_dict()
                click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                error.show()
            if standalone_mode:
                raise SystemExit(exit_code) from None
            return exit_code
        except Exception as error:
            if not json_mode:
                click.echo(f"Error: internal mechanism failure: {error}", err=True)
            else:
                payload = Result(
                    "cli",
                    "CLI=ERROR",
                    10,
                    resolve_workspace(workspace),
                    diagnostics=[
                        Diagnostic(
                            "internal_mechanism_failure",
                            f"{type(error).__name__}: {error}",
                        )
                    ],
                ).as_dict()
                click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            if standalone_mode:
                raise SystemExit(10) from None
            return 10
        if standalone_mode and isinstance(result, int):
            raise SystemExit(result)
        return result


def _result_with_command(
    result: Result, command: str, artifacts: list[Path] | None = None
) -> Result:
    return Result(
        command,
        result.token,
        result.exit_code,
        result.workspace,
        artifacts=artifacts if artifacts is not None else result.artifacts,
        diagnostics=result.diagnostics,
        next_steps=result.next_steps,
        data=result.data,
    )


def emit_result(state: State, result: Result) -> NoReturn:
    payload = result.as_dict()
    schema_errors = validate_contract("result-envelope", payload)
    if schema_errors:
        result = Result(
            result.command,
            "RESULT=ERROR",
            10,
            result.workspace,
            diagnostics=[
                Diagnostic("result_envelope_invalid", message) for message in schema_errors
            ],
        )
        payload = result.as_dict()
    if state.json_mode:
        click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        raise click.exceptions.Exit(result.exit_code)
    console = Console(highlight=False, markup=False)
    error_console = Console(highlight=False, markup=False, stderr=True)
    packet = result.data.get("packet")
    mermaid = result.data.get("mermaid")
    if packet:
        console.print(packet.rstrip())
    if mermaid:
        console.print(mermaid.rstrip())
    if (
        result.data
        and not packet
        and not mermaid
        and result.command
        in {
            "status",
            "next",
            "inspect",
            "doctor",
            "recipe schema",
        }
    ):
        console.print_json(json.dumps(result.data, ensure_ascii=False, sort_keys=True))
    for diagnostic in result.diagnostics:
        error_console.print(f"[{diagnostic.code}] {diagnostic.message}", style="red")
        if diagnostic.artifact:
            error_console.print(f"  {diagnostic.artifact}", style="dim")
        if diagnostic.detail:
            error_console.print(
                json.dumps(diagnostic.detail, ensure_ascii=False, sort_keys=True)[:2000],
                style="dim",
            )
    if result.artifacts:
        console.print(f"Artifacts: {len(result.artifacts)}", style="bold")
        for path in result.artifacts[:12]:
            console.print(f"  {path}")
        if len(result.artifacts) > 12:
            console.print(f"  … {len(result.artifacts) - 12} more")
    if result.next_steps:
        console.print("Next:", style="bold")
        for step in result.next_steps:
            console.print(f"  {step}")
    console.print(result.token, style="bold green" if result.ok else "bold yellow")
    raise click.exceptions.Exit(result.exit_code)


@click.group(cls=EnvelopeGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "workspace_option",
    "--workspace",
    type=click.Path(path_type=Path, file_okay=False),
    help="Workspace root.",
)
@click.option("json_mode", "--json", is_flag=True, help="Emit exactly one versioned JSON envelope.")
@click.option("dry_run", "--dry-run", is_flag=True, help="Validate and preview without writing.")
@click.version_option(VERSION, prog_name="seamwise")
@click.pass_context
def cli(
    context: click.Context,
    workspace_option: Path | None,
    json_mode: bool,
    dry_run: bool,
) -> None:
    """Compile Delivery Intent into reviewed, provable Task-Spec leaves."""

    context.obj = State(
        workspace=resolve_workspace(workspace_option), json_mode=json_mode, dry_run=dry_run
    )


@cli.command("init")
@click.option("--force", is_flag=True, help="Explicitly replace only the two starter documents.")
@pass_state
def init_command(state: State, force: bool) -> NoReturn:
    """Create a non-clobbering Seamwise workspace."""

    emit_result(
        state,
        init_workspace(state.workspace, force=force, dry_run=state.dry_run),
    )


@cli.group("recipe")
def recipe_group() -> None:
    """Inspect the exact authored recipe contract accepted by mapping."""


@recipe_group.command("schema")
@pass_state
def recipe_schema_command(state: State) -> NoReturn:
    """Locate the exact JSON Schema accepted by `map --source`."""

    path = schema_path("recipe")
    emit_result(
        state,
        Result(
            "recipe schema",
            "RECIPE_SCHEMA=READY",
            EXIT_OK,
            state.workspace,
            artifacts=[path],
            data={"schema": path.read_text(encoding="utf-8")},
        ),
    )


@cli.command("capabilities")
@pass_state
def capabilities_command(state: State) -> NoReturn:
    """Advertise the versioned contracts supported by this engine."""

    emit_result(
        state,
        Result(
            "capabilities",
            "CAPABILITIES=READY",
            EXIT_OK,
            state.workspace,
            data={
                "contract": "SeamwiseCapabilities/v1",
                "engine_version": VERSION,
                "engine_major": 0,
                "contracts": {
                    "cli_result": "SeamwiseCLIResult/v1",
                    "task_plan": "TaskPlan/v1",
                    "task_plan_lineage": "SeamwiseTaskPlanLineage/v1",
                    "delivery_plan_review": "DeliveryPlanReview/v1",
                },
                "commands": ["prepare", "review", "compile", "status"],
                "materializes_tasks": False,
                "dispatch_authority": False,
            },
        ),
    )


@cli.command("map")
@click.option(
    "--source", type=click.Path(path_type=Path, exists=True, dir_okay=False), required=True
)
@pass_state
def map_command(state: State, source: Path) -> NoReturn:
    """Lower authored intent and evidence into a validated seam map."""

    emit_result(state, map_recipe(state.workspace, source.resolve(), dry_run=state.dry_run))


@cli.command("plan")
@pass_state
def plan_command(state: State) -> NoReturn:
    """Lower seams into owning lanes and observable capability legs."""

    emit_result(state, build_plan(state.workspace, dry_run=state.dry_run))


@cli.command("review")
@click.option("--accept", is_flag=True, help="Explicitly accept the current delivery plan.")
@click.option("--reviewer", required=True, help="Identity accepting the plan.")
@click.option("--reason", required=True, help="Rationale for accepting the plan.")
@click.option("--fixture", is_flag=True, help="Label this receipt as test-fixture evidence.")
@pass_state
def review_command(
    state: State, accept: bool, reviewer: str, reason: str, fixture: bool
) -> NoReturn:
    """Record a hash-bound human acceptance; never runs implicitly."""

    if not accept:
        emit_result(
            state,
            Result(
                "review",
                PLAN_NEEDS_REVIEW,
                EXIT_NEEDS_INPUT,
                state.workspace,
                diagnostics=[
                    Diagnostic(
                        "explicit_acceptance_required", "Pass --accept to record acceptance."
                    )
                ],
            ),
        )
    emit_result(
        state,
        accept_plan(
            state.workspace,
            reviewer=reviewer,
            reason=reason,
            fixture=fixture,
            dry_run=state.dry_run,
        ),
    )


@cli.command("compile")
@pass_state
def compile_command(state: State) -> NoReturn:
    """Emit a reviewed TaskPlan and digest-bound lineage; create no Task-Specs."""

    emit_result(
        state,
        compile_graph(state.workspace, dry_run=state.dry_run),
    )


@cli.command("prepare")
@click.option("--source", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@pass_state
def prepare_command(state: State, source: Path | None) -> NoReturn:
    """Run missing transformations, stopping at the first authority gate."""

    artifacts: list[Path] = []
    current = stage_state(state.workspace)
    if current["issues"]:
        emit_result(
            state,
            Result(
                "prepare",
                "PREPARE=BLOCKED",
                4,
                state.workspace,
                diagnostics=[
                    Diagnostic(
                        item.get("code", "workspace_integrity_error"),
                        item.get("message", "Workspace integrity check failed."),
                        item.get("artifact"),
                        item.get("detail", {}),
                    )
                    for item in current["issues"]
                ],
                next_steps=["Resolve the reported integrity issue before continuing."],
            ),
        )
    if source is not None and current["seam_map"]:
        seam_map = load_yaml(state.workspace / "seamwise" / "seam-map.yaml")
        supplied_sha = sha256_file(source.resolve())
        mapped_sha = seam_map.get("source_recipe", {}).get("sha256")
        if supplied_sha != mapped_sha:
            emit_result(
                state,
                Result(
                    "prepare",
                    "PREPARE=SOURCE_CHANGED",
                    4,
                    state.workspace,
                    diagnostics=[
                        Diagnostic(
                            "source_recipe_changed",
                            "The supplied recipe differs from the hash-bound recipe already mapped in this workspace.",
                            str(source.resolve()),
                            {
                                "mapped_sha256": mapped_sha,
                                "supplied_sha256": supplied_sha,
                            },
                        )
                    ],
                    next_steps=[
                        "Start this revised recipe in a clean workspace; Seamwise never silently replaces reviewed projections in place."
                    ],
                ),
            )
    if not current["initialized"]:
        result = init_workspace(state.workspace, dry_run=state.dry_run)
        artifacts.extend(result.artifacts)
        if not result.ok or state.dry_run:
            emit_result(state, _result_with_command(result, "prepare", artifacts))
        current = stage_state(state.workspace)
    if not current["seam_map"]:
        if source is None:
            emit_result(
                state,
                Result(
                    "prepare",
                    "SEAM_MAP=NEEDS_DISCOVERY",
                    EXIT_NEEDS_INPUT,
                    state.workspace,
                    artifacts=artifacts,
                    diagnostics=[
                        Diagnostic("source_required", 'Provide --source "/path/to/recipe.yaml".')
                    ],
                    next_steps=['seamwise prepare --source "/path/to/recipe.yaml"'],
                ),
            )
        result = map_recipe(state.workspace, source.resolve(), dry_run=state.dry_run)
        artifacts.extend(result.artifacts)
        if not result.ok or state.dry_run:
            emit_result(state, _result_with_command(result, "prepare", artifacts))
        current = stage_state(state.workspace)
    if not current["delivery_plan"]:
        result = build_plan(state.workspace, dry_run=state.dry_run)
        artifacts.extend(result.artifacts)
        emit_result(state, _result_with_command(result, "prepare", artifacts))
    if not current["reviewed"]:
        plan = load_yaml(state.workspace / "seamwise" / "delivery-plan.yaml")
        emit_result(
            state,
            Result(
                "prepare",
                plan.get("status", PLAN_NEEDS_REVIEW),
                EXIT_NEEDS_INPUT,
                state.workspace,
                artifacts=artifacts,
                next_steps=[
                    'seamwise review --accept --reviewer "reviewer-name" --reason "review rationale"'
                ],
            ),
        )
    if not current["task_graph"]:
        result = compile_graph(
            state.workspace,
            dry_run=state.dry_run,
            command="prepare",
        )
        artifacts.extend(result.artifacts)
        emit_result(state, _result_with_command(result, "prepare", artifacts))
    emit_result(
        state,
        Result(
            "prepare",
            GRAPH_READY,
            EXIT_OK,
            state.workspace,
            next_steps=status_result(state.workspace).next_steps,
            data=current,
        ),
    )


@cli.command("status")
@pass_state
def status_command(state: State) -> NoReturn:
    """Show verified stage state and the exact next command."""

    emit_result(state, status_result(state.workspace))


@cli.command("next")
@pass_state
def next_command(state: State) -> NoReturn:
    """Print only the state-derived next action in a result envelope."""

    status = status_result(state.workspace)
    if not status.ok:
        emit_result(state, _result_with_command(status, "next"))
    emit_result(
        state,
        Result(
            "next",
            "NEXT=READY",
            EXIT_OK,
            state.workspace,
            next_steps=status.next_steps,
            data={"command": status.next_steps[0] if status.next_steps else None},
        ),
    )


@cli.command("inspect")
@click.argument("task_id", required=False)
@pass_state
def inspect_command(state: State, task_id: str | None) -> NoReturn:
    """Trace a TaskPlan unit back to intent, seam, lane, and leg."""

    emit_result(state, inspect_lineage(state.workspace, task_id))


@cli.command("graph")
@pass_state
def graph_command(state: State) -> NoReturn:
    """Render the current task graph as Mermaid."""

    with workspace_lock(state.workspace):
        plan, diagnostics = verify_plan(state.workspace)
        if plan is None:
            emit_result(
                state,
                Result(
                    "graph",
                    GRAPH_BLOCKED,
                    EXIT_INVALID,
                    state.workspace,
                    diagnostics=diagnostics,
                    next_steps=[
                        "seamwise plan",
                        "seamwise review --accept --reviewer <name> --reason <reason>",
                    ],
                ),
            )
        _, graph, graph_diagnostics = derive_task_bundle(state.workspace, plan)
        mermaid = render_graph_mermaid(graph)
    emit_result(
        state,
        Result(
            "graph",
            graph.get("status", GRAPH_BLOCKED),
            EXIT_OK if graph.get("status") == GRAPH_READY else EXIT_INVALID,
            state.workspace,
            diagnostics=graph_diagnostics,
            data={"graph": graph, "mermaid": mermaid},
        ),
    )


@cli.command("report")
@click.option("output_format", "--format", type=click.Choice(["html", "json"]), default="html")
@pass_state
def report_command(state: State, output_format: str) -> NoReturn:
    """Build a derived report; reports never authorize transitions."""

    emit_result(
        state,
        build_report(state.workspace, output_format=output_format, dry_run=state.dry_run),
    )


@cli.command("agent-context")
@click.option("--host", type=click.Choice(["codex", "claude", "chat"]), required=True)
@pass_state
def agent_context_command(state: State, host: str) -> NoReturn:
    """Emit a portable, versioned context packet for an agent host."""

    emit_result(state, build_agent_context(state.workspace, host=host))


@cli.command("install")
@click.argument("host", type=click.Choice(["codex", "claude", "all"]))
@click.option("--scope", type=click.Choice(["project", "user"]), default="project")
@click.option(
    "--target", type=click.Path(path_type=Path), help="Project root or test home override."
)
@pass_state
def install_command(
    state: State,
    host: str,
    scope: str,
    target: Path | None,
) -> NoReturn:
    """Install receipt-owned native skills for a supported host."""

    emit_result(
        state,
        run_install(
            state.workspace,
            host=host,
            scope=scope,
            target=target,
            dry_run=state.dry_run,
        ),
    )


@cli.command("uninstall")
@click.argument("host", type=click.Choice(["codex", "claude", "all"]))
@click.option("--scope", type=click.Choice(["project", "user"]), default="project")
@click.option(
    "--target", type=click.Path(path_type=Path), help="Project root or test home override."
)
@pass_state
def uninstall_command(state: State, host: str, scope: str, target: Path | None) -> NoReturn:
    """Remove only unchanged files owned by an installation receipt."""

    emit_result(
        state,
        run_uninstall(
            state.workspace,
            host=host,
            scope=scope,
            target=target,
            dry_run=state.dry_run,
        ),
    )


@cli.command("doctor")
@click.option("--host", type=click.Choice(["core", "codex", "claude", "all"]), default="core")
@click.option("--live", is_flag=True, help="Run explicit credentialed headless host probes.")
@click.option("--scope", type=click.Choice(["project", "user"]), default="project")
@click.option("--target", type=click.Path(path_type=Path))
@pass_state
def doctor_command(
    state: State, host: str, live: bool, scope: str, target: Path | None
) -> NoReturn:
    """Verify core contracts and optionally installed hosts."""

    emit_result(
        state,
        run_doctor(state.workspace, host=host, live=live, scope=scope, target=target),
    )


def main() -> None:
    cli(prog_name="seamwise")


if __name__ == "__main__":
    main()
