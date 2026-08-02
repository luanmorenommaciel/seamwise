"""Atomic Task Pack command surface required by the blueprint."""

from __future__ import annotations

from pathlib import Path

import click

from seamwise.constants import VERSION
from seamwise.safety import workspace_boundary_diagnostics
from seamwise.taskpack import direct_task_gate, new_task_spec
from seamwise.workspace import resolve_workspace


def _guard_workspace(root: Path) -> None:
    diagnostics = workspace_boundary_diagnostics(root)
    if diagnostics:
        for diagnostic in diagnostics:
            click.echo(f"{diagnostic.code}: {diagnostic.message}", err=True)
        raise click.exceptions.Exit(4)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("workspace", "--workspace", type=click.Path(path_type=Path, file_okay=False))
@click.version_option(VERSION, prog_name="task-spec")
@click.pass_context
def cli(context: click.Context, workspace: Path | None) -> None:
    """Create and gate Task-Spec files through the embedded Task Pack."""

    context.obj = resolve_workspace(workspace)


@cli.command("new")
@click.argument("slug")
@click.argument("effort", type=click.Choice(["XS", "S", "M", "L", "XL", "XXL"]))
@click.option("--profile", type=click.Choice(["lite", "standard", "full"]), default="standard")
@click.option("--source-note", default="human-input")
@click.pass_obj
def new_command(root: Path, slug: str, effort: str, profile: str, source_note: str) -> None:
    """Create a Task Pack template; generated TODOs are intentionally not valid yet."""

    _guard_workspace(root)
    process = new_task_spec(
        root, slug=slug, effort=effort, profile=profile, source_note=source_note
    )
    click.echo(process.stdout, nl=False)
    if process.stderr:
        click.echo(process.stderr, err=True, nl=False)
    raise click.exceptions.Exit(process.returncode)


@cli.command("validate")
@click.argument("path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.pass_obj
def validate_command(root: Path, path: Path) -> None:
    """Run the byte-preserved structural validator."""

    _guard_workspace(root)
    process = direct_task_gate(
        root, path=path, validate_only=True, stamp=False, reviewer="operator"
    )
    click.echo(process.stdout, nl=False)
    if process.stderr:
        click.echo(process.stderr, err=True, nl=False)
    raise click.exceptions.Exit(process.returncode)


@cli.command("gate")
@click.argument("path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--stamp", is_flag=True, help="Explicitly stamp the Task-Spec if the gate passes.")
@click.option("--reviewer", default="operator")
@click.pass_obj
def gate_command(root: Path, path: Path, stamp: bool, reviewer: str) -> None:
    """Run PRE; --stamp is the only authority-bearing mode."""

    _guard_workspace(root)
    process = direct_task_gate(root, path=path, validate_only=False, stamp=stamp, reviewer=reviewer)
    click.echo(process.stdout, nl=False)
    if process.stderr:
        click.echo(process.stderr, err=True, nl=False)
    raise click.exceptions.Exit(process.returncode)


def main() -> None:
    cli(prog_name="task-spec")


if __name__ == "__main__":
    main()
