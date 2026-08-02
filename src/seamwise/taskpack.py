"""Thin adapter over the byte-preserved Task Pack."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.resources
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from seamwise.constants import (
    EXIT_CONFLICT,
    EXIT_INVALID,
    EXIT_NEEDS_INPUT,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    GRAPH_READY,
    SPECS_ERROR,
    SPECS_INVALID,
    SPECS_PREFLIGHT,
    SPECS_SEALED,
    SPECS_VALID,
)
from seamwise.contracts import validate_contract
from seamwise.io import (
    TransactionWriter,
    UnsafeWriteTargetError,
    dump_json,
    load_frontmatter,
    load_json,
    load_yaml,
    sha256_bytes,
    sha256_file,
    workspace_lock,
)
from seamwise.result import Diagnostic, Result
from seamwise.safety import path_boundary_diagnostics, workspace_boundary_diagnostics

SEAMWISE_SKILLS = (
    "seamwise",
    "to-seam-map",
    "to-delivery-plan",
    "to-task-graph",
    "to-task-specs",
)

CANONICAL_SKILLS = (
    *SEAMWISE_SKILLS,
    "task-spec",
)


class _SigningKeyUnavailable(RuntimeError):
    """The Task Pack could not create the required Tier-1 authority envelope."""


def source_repository_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "skills" / "task-spec" / "SKILL.md").is_file():
        return candidate
    return None


def assets_root() -> Path:
    source = source_repository_root()
    if source is not None:
        return source
    resource = importlib.resources.files("seamwise").joinpath("assets")
    return Path(str(resource))


def task_pack_root() -> Path:
    return assets_root() / "skills" / "task-spec"


def skills_root() -> Path:
    return assets_root() / "skills"


def verify_task_pack() -> list[Diagnostic]:
    root = assets_root()
    manifest_path = root / "vendor" / "task-pack-source.json"
    task_pack = root / "skills" / "task-spec"
    if not manifest_path.is_file():
        return [Diagnostic("task_pack_manifest_missing", f"Missing {manifest_path}")]
    if not task_pack.is_dir():
        return [Diagnostic("task_pack_missing", f"Missing {task_pack}")]
    diagnostics: list[Diagnostic] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [Diagnostic("task_pack_manifest_invalid", str(error), str(manifest_path))]
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        return [
            Diagnostic(
                "task_pack_manifest_invalid",
                "Task Pack manifest has an invalid structure.",
                str(manifest_path),
            )
        ]
    actual_paths = {
        str(path.relative_to(task_pack)) for path in task_pack.rglob("*") if path.is_file()
    }
    expected_paths = set(manifest["files"])
    if actual_paths != expected_paths:
        diagnostics.append(
            Diagnostic(
                "task_pack_inventory_mismatch",
                "Task Pack paths differ from the Phase-0 manifest.",
                detail={
                    "missing": sorted(expected_paths - actual_paths),
                    "extra": sorted(actual_paths - expected_paths),
                },
            )
        )
    for relative in sorted(actual_paths & expected_paths):
        path = task_pack / relative
        expected = manifest["files"][relative]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        mode = format(stat.S_IMODE(path.stat().st_mode), "04o")
        if digest != expected["sha256"] or mode != expected["mode"]:
            diagnostics.append(
                Diagnostic(
                    "task_pack_byte_mismatch",
                    f"Task Pack file drifted: {relative}",
                    str(path),
                    {
                        "expected_sha256": expected["sha256"],
                        "actual_sha256": digest,
                        "expected_mode": expected["mode"],
                        "actual_mode": mode,
                    },
                )
            )
    return diagnostics


def _specs(root: Path, explicit: tuple[Path, ...] = ()) -> list[Path]:
    if explicit:
        return [path.resolve() for path in explicit]
    return sorted((root / "tasks").glob("T-*.md"))


def _run(script: str, root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    executable = task_pack_root() / "scripts" / script
    integrity_diagnostics = verify_task_pack()
    if integrity_diagnostics:
        message = "\n".join(f"{item.code}: {item.message}" for item in integrity_diagnostics)
        return subprocess.CompletedProcess(
            ["bash", str(executable), *arguments],
            returncode=1,
            stdout="",
            stderr=f"Task Pack integrity check failed:\n{message}\n",
        )
    environment = os.environ.copy()
    environment["TASKSPEC_BACKLOG_DIR"] = str((root / "tasks").resolve())
    return subprocess.run(
        ["bash", str(executable), *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _normalize_sealed_authority_fields(actual: str, expected: str) -> str:
    """Restore only Task Pack seal fields before projection comparison."""

    if actual == expected:
        return actual
    try:
        actual_frontmatter, actual_body = actual[4:].split("\n---\n", 1)
        expected_frontmatter, _ = expected[4:].split("\n---\n", 1)
        parsed = yaml.safe_load(actual_frontmatter)
    except (ValueError, yaml.YAMLError):
        return actual
    if not isinstance(parsed, dict) or parsed.get("signed_off") is not True:
        return actual
    authority_fields = {"signed_off", "signed_off_by", "signed_off_at"}
    expected_lines = {
        line.split(":", 1)[0]: line
        for line in expected_frontmatter.splitlines()
        if line.split(":", 1)[0] in authority_fields
    }
    normalized: list[str] = []
    for line in actual_frontmatter.splitlines():
        field = line.split(":", 1)[0]
        if field == "signed_off_sig":
            continue
        normalized.append(expected_lines.get(field, line))
    return "---\n" + "\n".join(normalized) + "\n---\n" + actual_body


def verify_task_bundle(
    root: Path, *, paths: tuple[Path, ...] = ()
) -> tuple[list[Path], dict[str, Any] | None, list[Diagnostic]]:
    """Verify graph, review, lineage, exact spec inventory, and every bound hash."""

    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return [], None, boundary_diagnostics
    with workspace_lock(root):
        return _verify_task_bundle_unlocked(root, paths=paths)


def _verify_task_bundle_unlocked(
    root: Path, *, paths: tuple[Path, ...] = ()
) -> tuple[list[Path], dict[str, Any] | None, list[Diagnostic]]:
    """Verify a task bundle while the caller owns the workspace lock."""

    from seamwise.engine import derive_task_bundle, render_graph_mermaid, verify_plan

    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return [], None, boundary_diagnostics
    graph_path = root / "tasks" / "task-graph.yaml"
    lineage_path = root / "tasks" / "task-lineage.json"
    diagnostics: list[Diagnostic] = []
    plan, plan_diagnostics = verify_plan(root)
    diagnostics.extend(plan_diagnostics)
    if not graph_path.is_file():
        diagnostics.append(Diagnostic("task_graph_missing", "Compile the task graph first."))
    if not lineage_path.is_file():
        diagnostics.append(Diagnostic("task_lineage_missing", "Task lineage is missing."))
    if diagnostics:
        return [], None, diagnostics
    try:
        graph = load_yaml(graph_path)
        lineage = load_json(lineage_path)
    except (OSError, ValueError) as error:
        return [], None, [Diagnostic("compiled_artifact_invalid", str(error))]
    diagnostics.extend(
        Diagnostic("task_graph_schema", message, str(graph_path))
        for message in validate_contract("task-graph", graph)
    )
    diagnostics.extend(
        Diagnostic("task_lineage_schema", message, str(lineage_path))
        for message in validate_contract("task-lineage", lineage)
    )
    if diagnostics or not isinstance(graph, dict) or not isinstance(lineage, dict):
        return [], None, diagnostics
    assert plan is not None
    _, expected_graph, expected_lineage, expected_specs, derivation_diagnostics = (
        derive_task_bundle(root, plan, task_pack_root())
    )
    diagnostics.extend(derivation_diagnostics)
    if expected_lineage is None:
        diagnostics.append(
            Diagnostic(
                "task_projection_unprovable",
                "The reviewed plan no longer derives a complete Task-Spec bundle.",
            )
        )
    else:
        if graph != expected_graph:
            diagnostics.append(
                Diagnostic(
                    "task_graph_projection_mismatch",
                    "Task graph does not exactly match deterministic reconstruction from the reviewed plan.",
                    str(graph_path),
                )
            )
        comparable_lineage = json.loads(json.dumps(lineage))
        for task_id, expected_entry in expected_lineage["tasks"].items():
            actual_entry = comparable_lineage.get("tasks", {}).get(task_id)
            if isinstance(actual_entry, dict):
                actual_entry["spec_sha256"] = expected_entry["spec_sha256"]
        if comparable_lineage != expected_lineage:
            diagnostics.append(
                Diagnostic(
                    "task_lineage_projection_mismatch",
                    "Task lineage does not exactly match deterministic reconstruction from the reviewed plan.",
                    str(lineage_path),
                )
            )
        for task_id, expected_content in expected_specs.items():
            spec_path = root / "tasks" / f"{task_id}.md"
            if not spec_path.is_file():
                continue
            try:
                actual_content = spec_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if (
                _normalize_sealed_authority_fields(actual_content, expected_content)
                != expected_content
            ):
                diagnostics.append(
                    Diagnostic(
                        "task_spec_projection_mismatch",
                        f"Task-Spec {task_id} does not exactly match deterministic reconstruction from the reviewed plan.",
                        str(spec_path),
                    )
                )
    if graph.get("status") != GRAPH_READY:
        diagnostics.append(Diagnostic("task_graph_not_ready", "Task graph is not ready."))
    mermaid_path = root / "tasks" / "critical-path.mmd"
    rendered_mermaid = render_graph_mermaid(graph)
    rendered_hash = hashlib.sha256(rendered_mermaid.encode("utf-8")).hexdigest()
    if (
        graph.get("critical_path_mermaid_sha256") != rendered_hash
        or not mermaid_path.is_file()
        or sha256_file(mermaid_path) != rendered_hash
    ):
        diagnostics.append(
            Diagnostic("critical_path_hash_mismatch", "Critical-path Mermaid is stale or changed.")
        )
    plan_sha = sha256_file(root / "seamwise" / "delivery-plan.yaml")
    if graph.get("plan_sha256") != plan_sha or lineage.get("plan_sha256") != plan_sha:
        diagnostics.append(
            Diagnostic("compiled_plan_hash_mismatch", "Graph or lineage is stale for this plan.")
        )
    graph_nodes = {
        item.get("id"): item for item in graph.get("nodes", []) if isinstance(item, dict)
    }
    lineage_tasks = lineage.get("tasks", {})
    if set(graph_nodes) != set(lineage_tasks):
        diagnostics.append(
            Diagnostic("task_inventory_mismatch", "Graph and lineage task IDs differ.")
        )
    plan_legs = (
        {item.get("id"): item for item in plan.get("legs", []) if isinstance(item, dict)}
        if plan
        else {}
    )
    expected_paths: dict[str, Path] = {}
    for task_id, entry in lineage_tasks.items():
        expected = (root / "tasks" / f"{task_id}.md").resolve()
        raw = entry.get("spec")
        if not isinstance(raw, str) or Path(raw).is_absolute():
            diagnostics.append(
                Diagnostic("task_spec_path_invalid", f"Task-Spec path is invalid for {task_id}.")
            )
            continue
        actual = (root / raw).resolve()
        if raw != f"tasks/{task_id}.md" or actual != expected:
            diagnostics.append(
                Diagnostic("task_spec_path_invalid", f"Task-Spec path escapes for {task_id}.")
            )
            continue
        expected_paths[task_id] = expected
        if not expected.is_file() or sha256_file(expected) != entry.get("spec_sha256"):
            diagnostics.append(
                Diagnostic(
                    "task_spec_hash_mismatch",
                    f"Task-Spec {task_id} changed after compilation.",
                    str(expected),
                )
            )
        node = graph_nodes.get(task_id, {})
        if any(
            node.get(node_key) != entry.get(lineage_key)
            for node_key, lineage_key in (
                ("seam_id", "seam"),
                ("swimlane_id", "swimlane"),
                ("leg_id", "leg"),
            )
        ):
            diagnostics.append(
                Diagnostic("task_lineage_mismatch", f"Graph lineage differs for {task_id}.")
            )
        leg = plan_legs.get(entry.get("leg"), {})
        if leg.get("sha256") != entry.get("source_sha256"):
            diagnostics.append(
                Diagnostic("task_source_hash_mismatch", f"Task source differs for {task_id}.")
            )
    actual_paths = {path.resolve() for path in (root / "tasks").glob("T-*.md")}
    if actual_paths != set(expected_paths.values()):
        diagnostics.append(
            Diagnostic(
                "stale_or_unowned_task_specs",
                "Task-Spec inventory does not exactly match lineage.",
                detail={
                    "missing": sorted(
                        str(path) for path in set(expected_paths.values()) - actual_paths
                    ),
                    "extra": sorted(
                        str(path) for path in actual_paths - set(expected_paths.values())
                    ),
                },
            )
        )
    selected = sorted(expected_paths.values())
    if paths:
        requested = [path.resolve() for path in paths]
        unknown = [path for path in requested if path not in expected_paths.values()]
        if unknown:
            diagnostics.append(
                Diagnostic(
                    "task_spec_not_lineage_owned",
                    "Explicit paths must name compiled, lineage-owned Task-Specs.",
                    detail={"paths": [str(path) for path in unknown]},
                )
            )
        selected = requested
    return ([], None, diagnostics) if diagnostics else (selected, lineage, [])


def _receipt_path(root: Path, check: str) -> Path:
    return root / "tasks" / ("preflight.json" if check == "preflight" else "validation.json")


def _check_receipt(root: Path, check: str, specs: list[Path]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "check": check,
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "lineage_sha256": sha256_file(root / "tasks" / "task-lineage.json"),
        "specs": {path.stem: sha256_file(path) for path in specs},
        "authorization": False,
    }


def verify_check_receipt(root: Path, check: str, specs: list[Path]) -> list[Diagnostic]:
    path = _receipt_path(root, check)
    if not path.is_file():
        return [Diagnostic(f"{check}_receipt_missing", f"Run tasks {check} first.", str(path))]
    try:
        receipt = load_json(path)
    except (OSError, ValueError) as error:
        return [Diagnostic(f"{check}_receipt_invalid", str(error), str(path))]
    diagnostics = [
        Diagnostic(f"{check}_receipt_invalid", message, str(path))
        for message in validate_contract("task-check-receipt", receipt)
    ]
    if not isinstance(receipt, dict):
        return diagnostics
    expected = {item.stem: sha256_file(item) for item in specs}
    if receipt.get("check") != check or receipt.get("specs") != expected:
        diagnostics.append(
            Diagnostic(f"{check}_receipt_stale", f"Task {check} receipt is stale.", str(path))
        )
    lineage_path = root / "tasks" / "task-lineage.json"
    if not lineage_path.is_file() or receipt.get("lineage_sha256") != sha256_file(lineage_path):
        diagnostics.append(
            Diagnostic(f"{check}_lineage_stale", f"Task {check} lineage hash is stale.", str(path))
        )
    return diagnostics


def verify_tier1_seals(root: Path, specs: list[Path]) -> tuple[int, int, list[Diagnostic]]:
    """Cryptographically verify every claimed Task-Spec seal without running evals.

    A textual ``signed_off`` marker is not authority.  The embedded Task Pack
    validator recomputes the HMAC using the current workspace key; status may
    report dispatch readiness only for an explicit Tier-1 verification.
    """

    verified = 0
    claimed = 0
    diagnostics: list[Diagnostic] = []
    for spec in specs:
        try:
            frontmatter, _ = load_frontmatter(spec)
        except (OSError, ValueError, yaml.YAMLError) as error:
            diagnostics.append(Diagnostic("task_spec_seal_invalid", str(error), str(spec)))
            continue
        if frontmatter.get("signed_off") is not True:
            continue
        claimed += 1
        process = _run(
            "validate-task-spec.sh",
            root,
            ["--no-state", "--skip-touches-paths", str(spec)],
        )
        if process.returncode == 0 and "OK(Tier 1):" in process.stdout:
            verified += 1
            continue
        if process.returncode == 0:
            diagnostics.append(
                Diagnostic(
                    "tier1_verification_unavailable",
                    "A signed Task-Spec could not be verified as Tier 1 with the current signing key.",
                    str(spec),
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    "tier1_signature_invalid",
                    "A signed Task-Spec failed cryptographic or structural verification.",
                    str(spec),
                )
            )
    return verified, claimed, diagnostics


def _required_tools(specs: list[Path]) -> set[str]:
    required: set[str] = set()
    pattern = re.compile(r"^  required_tools:\s*(\[[^\n]+\])\s*$", re.MULTILINE)
    for spec in specs:
        match = pattern.search(spec.read_text(encoding="utf-8"))
        if match:
            value = yaml.safe_load(match.group(1))
            if isinstance(value, list):
                required.update(str(item) for item in value)
    return required


def validate_task_specs(
    root: Path,
    *,
    paths: tuple[Path, ...] = (),
    preflight: bool = False,
    seal: bool = False,
    reviewer: str | None = None,
    dry_run: bool = False,
    execute_evals: bool = False,
) -> Result:
    command = "tasks seal" if seal else "tasks preflight" if preflight else "tasks validate"
    integrity_diagnostics = verify_task_pack()
    if integrity_diagnostics:
        return Result(
            command,
            SPECS_ERROR,
            EXIT_CONFLICT,
            root,
            diagnostics=integrity_diagnostics,
            next_steps=["Restore the byte-pinned Task Pack before running any gate."],
        )
    specs, lineage, bundle_diagnostics = verify_task_bundle(root, paths=paths)
    if bundle_diagnostics:
        return Result(
            command,
            SPECS_INVALID,
            EXIT_CONFLICT,
            root,
            diagnostics=bundle_diagnostics,
            next_steps=["seamwise compile"],
        )
    if seal and lineage is not None and lineage.get("fixture") is True:
        return Result(
            command,
            SPECS_INVALID,
            EXIT_NEEDS_INPUT,
            root,
            diagnostics=[
                Diagnostic(
                    "fixture_cannot_create_dispatch_authority",
                    "Fixture-reviewed Task-Specs cannot be sealed. Rebuild from a non-fixture human review.",
                )
            ],
        )
    initial_hashes = {path: sha256_file(path) for path in specs}
    if shutil.which("bash") is None:
        return Result(
            command,
            SPECS_ERROR,
            EXIT_UNAVAILABLE,
            root,
            diagnostics=[Diagnostic("bash_unavailable", "Task Pack requires bash.")],
        )
    if preflight and not seal and not dry_run and not execute_evals:
        return Result(
            command,
            SPECS_INVALID,
            EXIT_NEEDS_INPUT,
            root,
            diagnostics=[
                Diagnostic(
                    "eval_execution_acknowledgement_required",
                    "Preflight executes authored eval Bash in the workspace. Review the specs, then acknowledge execution.",
                )
            ],
            next_steps=["seamwise tasks preflight --acknowledge-eval-execution"],
        )
    if seal and not dry_run and not execute_evals:
        return Result(
            command,
            SPECS_INVALID,
            EXIT_NEEDS_INPUT,
            root,
            diagnostics=[
                Diagnostic(
                    "seal_eval_execution_acknowledgement_required",
                    "The pinned Task Pack stamping gate executes authored eval Bash according to Task Pack semantics. Review the evals and acknowledge that execution explicitly.",
                )
            ],
            next_steps=[
                'seamwise tasks seal --reviewer "human-reviewer" --acknowledge-eval-execution --acknowledge-dispatch-authority'
            ],
        )
    if (preflight or seal) and shutil.which("shellcheck") is None:
        return Result(
            command,
            SPECS_ERROR,
            EXIT_UNAVAILABLE,
            root,
            diagnostics=[
                Diagnostic(
                    "shellcheck_unavailable",
                    "Task-Spec preflight requires shellcheck; install it and retry.",
                )
            ],
        )
    if preflight or seal:
        missing_tools = sorted(
            tool for tool in _required_tools(specs) if shutil.which(tool) is None
        )
        if missing_tools:
            return Result(
                command,
                SPECS_ERROR,
                EXIT_UNAVAILABLE,
                root,
                diagnostics=[
                    Diagnostic(
                        "required_tool_unavailable",
                        "Task-Spec preflight requires unavailable tools: "
                        + ", ".join(missing_tools),
                    )
                ],
            )
    if seal:
        all_specs, _, all_diagnostics = verify_task_bundle(root)
        if all_diagnostics:
            return Result(
                command,
                SPECS_INVALID,
                EXIT_CONFLICT,
                root,
                diagnostics=all_diagnostics,
            )
        receipt_diagnostics = verify_check_receipt(root, "preflight", all_specs)
        if receipt_diagnostics:
            return Result(
                command,
                SPECS_INVALID,
                EXIT_NEEDS_INPUT,
                root,
                diagnostics=receipt_diagnostics,
                next_steps=["seamwise tasks preflight --acknowledge-eval-execution"],
            )

    def run_gate(spec: Path, *, stamp: bool = False) -> subprocess.CompletedProcess[str]:
        if stamp:
            return _run(
                "safe-to-delegate.sh",
                root,
                [
                    "--skip-touches-paths",
                    "--stamp",
                    "--stamp-by",
                    reviewer or "operator",
                    "--require-tier1",
                    str(spec),
                ],
            )
        if (preflight or seal) and dry_run:
            return _run(
                "validate-task-spec.sh",
                root,
                ["--no-state", "--shellcheck-evals", "--skip-touches-paths", str(spec)],
            )
        if seal:
            return _run(
                "validate-task-spec.sh",
                root,
                ["--no-state", "--shellcheck-evals", "--skip-touches-paths", str(spec)],
            )
        if preflight:
            return _run("safe-to-delegate.sh", root, ["--skip-touches-paths", str(spec)])
        return _run(
            "validate-task-spec.sh",
            root,
            ["--no-state", "--skip-touches-paths", str(spec)],
        )

    diagnostics: list[Diagnostic] = []
    transcripts: list[dict[str, Any]] = []
    for spec in specs:
        process = run_gate(spec)
        transcripts.append(
            {
                "spec": str(spec),
                "exit_code": process.returncode,
                "stdout": process.stdout.strip().splitlines()[-10:],
                "stderr": process.stderr.strip().splitlines()[-10:],
            }
        )
        if process.returncode != 0:
            diagnostics.append(
                Diagnostic(
                    "task_pack_gate_failed",
                    f"Task Pack rejected {spec.name}.",
                    str(spec),
                    {
                        "exit_code": process.returncode,
                        "stdout": process.stdout[-2000:],
                        "stderr": process.stderr[-2000:],
                    },
                )
            )
    changed_during_gate = [
        path
        for path, digest in initial_hashes.items()
        if not path.is_file() or sha256_file(path) != digest
    ]
    if changed_during_gate:
        diagnostics.append(
            Diagnostic(
                "task_spec_changed_during_gate",
                "Task-Specs changed while the gate was running; no receipt was written.",
                detail={"paths": [str(path) for path in changed_during_gate]},
            )
        )
    if diagnostics:
        return Result(
            command,
            SPECS_INVALID,
            EXIT_INVALID,
            root,
            artifacts=specs,
            diagnostics=diagnostics,
            data={
                "count": len(specs),
                "task_pack": str(task_pack_root()),
                "transcripts": transcripts,
            },
        )

    if seal and dry_run:
        return Result(
            command,
            SPECS_VALID,
            EXIT_OK,
            root,
            artifacts=specs,
            next_steps=[
                "Rerun without --dry-run only after explicitly choosing to create dispatch authority."
            ],
            data={
                "count": len(specs),
                "task_pack": str(task_pack_root()),
                "transcripts": transcripts,
                "dry_run": True,
                "would_seal": [str(path) for path in specs],
            },
        )

    if seal:
        assert lineage is not None
        lineage_path = root / "tasks" / "task-lineage.json"
        stamp_transcripts: list[dict[str, Any]] = []
        try:
            sealed_contents: dict[Path, str] = {}
            with tempfile.TemporaryDirectory(
                prefix=".seamwise-seal-", dir=root / "tasks"
            ) as temporary:
                temporary_root = Path(temporary)
                for spec in specs:
                    staged_spec = temporary_root / spec.name
                    shutil.copy2(spec, staged_spec)
                    process = run_gate(staged_spec, stamp=True)
                    stamp_transcripts.append(
                        {
                            "spec": str(spec),
                            "exit_code": process.returncode,
                            "stdout": process.stdout.strip().splitlines()[-10:],
                            "stderr": process.stderr.strip().splitlines()[-10:],
                        }
                    )
                    combined_output = f"{process.stdout}\n{process.stderr}"
                    if "no signing key resolved" in combined_output.lower():
                        raise _SigningKeyUnavailable(
                            "No Task-Spec signing key is available for Tier-1 sealing."
                        )
                    if process.returncode != 0 or "TIER=1" not in process.stdout:
                        raise RuntimeError(
                            f"Task Pack could not create Tier-1 seal for {spec.name}"
                        )
                    sealed_contents[spec] = staged_spec.read_text(encoding="utf-8")
            updated_lineage = json.loads(json.dumps(lineage))
            for spec, content in sealed_contents.items():
                updated_lineage["tasks"][spec.stem]["spec_sha256"] = sha256_bytes(
                    content.encode("utf-8")
                )
            errors = validate_contract("task-lineage", updated_lineage)
            if errors:
                raise RuntimeError("sealed lineage is invalid: " + "; ".join(errors))
            all_hashes = {
                task_id: entry["spec_sha256"] for task_id, entry in updated_lineage["tasks"].items()
            }
            lineage_digest = sha256_bytes(dump_json(updated_lineage).encode("utf-8"))
            refreshed_receipts = {
                check: {
                    "schema_version": 1,
                    "check": check,
                    "checked_at": dt.datetime.now(dt.UTC).isoformat(),
                    "lineage_sha256": lineage_digest,
                    "specs": all_hashes,
                    "authorization": False,
                }
                for check in ("validate", "preflight")
            }
            with workspace_lock(root):
                current_specs, _, current_diagnostics = _verify_task_bundle_unlocked(
                    root, paths=paths
                )
                if (
                    current_diagnostics
                    or {path: sha256_file(path) for path in current_specs} != initial_hashes
                ):
                    raise RuntimeError("Task-Spec bundle changed while sealing")
                current_all, _, current_all_diagnostics = _verify_task_bundle_unlocked(root)
                current_receipt_diagnostics = verify_check_receipt(root, "preflight", current_all)
                if current_all_diagnostics or current_receipt_diagnostics:
                    raise RuntimeError("Preflight receipt changed while sealing")
                transaction = TransactionWriter()
                for spec, content in sealed_contents.items():
                    transaction.text(spec, content)
                transaction.json(lineage_path, updated_lineage)
                for check, receipt in refreshed_receipts.items():
                    transaction.json(_receipt_path(root, check), receipt)
                transaction.commit()
        except _SigningKeyUnavailable as error:
            return Result(
                command,
                SPECS_INVALID,
                EXIT_NEEDS_INPUT,
                root,
                diagnostics=[Diagnostic("signing_key_unavailable", str(error))],
                next_steps=["seamwise tasks setup-signing-key"],
                data={"transcripts": [*transcripts, *stamp_transcripts]},
            )
        except Exception as error:
            return Result(
                command,
                SPECS_INVALID,
                EXIT_CONFLICT,
                root,
                diagnostics=[Diagnostic("seal_transaction_blocked", str(error))],
                data={"transcripts": [*transcripts, *stamp_transcripts]},
            )
        transcripts.extend(stamp_transcripts)

    token = (
        SPECS_SEALED
        if seal
        else SPECS_VALID
        if dry_run
        else SPECS_PREFLIGHT
        if preflight
        else SPECS_VALID
    )
    if not seal and not dry_run and not paths:
        check = "preflight" if preflight else "validate"
        with workspace_lock(root):
            current_specs, _, current_diagnostics = _verify_task_bundle_unlocked(root)
            if (
                current_diagnostics
                or {path: sha256_file(path) for path in current_specs} != initial_hashes
            ):
                return Result(
                    command,
                    SPECS_INVALID,
                    EXIT_CONFLICT,
                    root,
                    diagnostics=[
                        Diagnostic(
                            "task_bundle_changed_during_gate",
                            "Task bundle changed before the check receipt could be committed.",
                        )
                    ],
                )
            receipt = _check_receipt(root, check, current_specs)
            errors = validate_contract("task-check-receipt", receipt)
            if errors:
                return Result(
                    command,
                    SPECS_ERROR,
                    EXIT_INVALID,
                    root,
                    diagnostics=[Diagnostic("task_check_receipt_invalid", item) for item in errors],
                )
            transaction = TransactionWriter()
            transaction.json(_receipt_path(root, check), receipt)
            try:
                transaction.commit()
            except UnsafeWriteTargetError as error:
                return Result(
                    command,
                    SPECS_INVALID,
                    EXIT_CONFLICT,
                    root,
                    diagnostics=[Diagnostic("unsafe_write_target", str(error))],
                )
    return Result(
        command,
        token,
        EXIT_OK if not diagnostics else EXIT_INVALID,
        root,
        artifacts=specs,
        diagnostics=diagnostics,
        next_steps=(
            [
                "Rerun without --dry-run and acknowledge eval execution only after reviewing every eval body."
            ]
            if dry_run
            else ["Dispatch only within the Tier-1 authority and review boundary."]
            if seal
            else [
                "Review every eval body, then run: seamwise tasks preflight --acknowledge-eval-execution"
            ]
            if not preflight
            else [
                "Review/select drafts; configure a Task-Spec signing key before the explicit tasks seal command."
            ]
        ),
        data={
            "count": len(specs),
            "task_pack": str(task_pack_root()),
            "transcripts": transcripts,
            "dry_run": dry_run,
            "would_execute_evals": [str(path) for path in specs]
            if dry_run and (preflight or seal)
            else [],
        },
    )


def new_task_spec(
    root: Path,
    *,
    slug: str,
    effort: str,
    profile: str,
    source_note: str,
) -> subprocess.CompletedProcess[str]:
    return _run(
        "generate-task-spec.sh",
        root,
        [f"--profile={profile}", slug, effort, "any", source_note],
    )


def direct_task_gate(
    root: Path,
    *,
    path: Path,
    validate_only: bool,
    stamp: bool,
    reviewer: str,
) -> subprocess.CompletedProcess[str]:
    if validate_only:
        return _run("validate-task-spec.sh", root, ["--no-state", str(path.resolve())])
    arguments = [str(path.resolve())]
    if stamp:
        arguments = ["--stamp", "--stamp-by", reviewer, str(path.resolve())]
    return _run("safe-to-delegate.sh", root, arguments)


def setup_signing_key(root: Path, *, force: bool = False, dry_run: bool = False) -> Result:
    """Provision one repo-local Task Pack HMAC key outside version control."""

    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result(
            "tasks setup-signing-key",
            "SIGNING_KEY=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=boundary_diagnostics,
        )
    integrity_diagnostics = verify_task_pack()
    if integrity_diagnostics:
        return Result(
            "tasks setup-signing-key",
            "SIGNING_KEY=ERROR",
            EXIT_CONFLICT,
            root,
            diagnostics=integrity_diagnostics,
        )
    if shutil.which("git") is None or shutil.which("bash") is None:
        return Result(
            "tasks setup-signing-key",
            "SIGNING_KEY=UNAVAILABLE",
            EXIT_UNAVAILABLE,
            root,
            diagnostics=[Diagnostic("signing_key_tools_unavailable", "Git and Bash are required.")],
        )
    git_process = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if git_process.returncode != 0 or not git_process.stdout.strip():
        return Result(
            "tasks setup-signing-key",
            "SIGNING_KEY=UNAVAILABLE",
            EXIT_UNAVAILABLE,
            root,
            diagnostics=[
                Diagnostic(
                    "git_directory_unavailable",
                    "A Git workspace is required so the secret can remain outside version control.",
                )
            ],
        )
    raw_git_dir = Path(git_process.stdout.strip())
    git_dir = Path(
        os.path.abspath(raw_git_dir if raw_git_dir.is_absolute() else root / raw_git_dir)
    )
    key_path = git_dir / "info" / "taskspec-signing-key"
    key_boundary = path_boundary_diagnostics(
        git_dir,
        [git_dir / "info", key_path],
        code="unsafe_signing_key_path",
    )
    if key_boundary:
        return Result(
            "tasks setup-signing-key",
            "SIGNING_KEY=BLOCKED",
            EXIT_CONFLICT,
            root,
            diagnostics=key_boundary,
        )
    with workspace_lock(root, dry_run=dry_run):
        locked_boundary = path_boundary_diagnostics(
            git_dir,
            [git_dir / "info", key_path],
            code="unsafe_signing_key_path",
        )
        if locked_boundary:
            return Result(
                "tasks setup-signing-key",
                "SIGNING_KEY=BLOCKED",
                EXIT_CONFLICT,
                root,
                diagnostics=locked_boundary,
            )
        if (key_path.exists() or key_path.is_symlink()) and not force:
            valid_key = False
            mode: int | None = None
            try:
                mode = stat.S_IMODE(key_path.lstat().st_mode)
                content = key_path.read_text(encoding="utf-8").strip()
                valid_key = (
                    not key_path.is_symlink()
                    and key_path.is_file()
                    and mode == 0o600
                    and re.fullmatch(r"[0-9A-Fa-f]{64}", content) is not None
                )
            except OSError:
                content = ""
            if not valid_key:
                return Result(
                    "tasks setup-signing-key",
                    "SIGNING_KEY=BLOCKED",
                    EXIT_CONFLICT,
                    root,
                    diagnostics=[
                        Diagnostic(
                            "signing_key_permissions_invalid",
                            "Existing signing key must be a non-symlink regular file with mode 0600 and exactly 64 hexadecimal characters.",
                            str(key_path),
                            {"mode": format(mode, "04o") if mode is not None else None},
                        )
                    ],
                )
            return Result(
                "tasks setup-signing-key",
                "SIGNING_KEY=READY",
                EXIT_OK,
                root,
                artifacts=[key_path],
                next_steps=["Run seamwise status; Tier-1 signatures can now be verified."],
                data={"created": False, "dry_run": dry_run, "rotation": False},
            )
        if dry_run:
            return Result(
                "tasks setup-signing-key",
                "SIGNING_KEY=WOULD_CREATE",
                EXIT_OK,
                root,
                artifacts=[key_path],
                next_steps=["Rerun this exact command without global --dry-run."],
                data={"created": False, "dry_run": True, "rotation": force},
            )
        script = task_pack_root() / "configs" / "setup-taskspec-signing-key.sh"
        arguments = ["bash", str(script)]
        if force:
            arguments.append("--force")
        generated = subprocess.run(
            arguments,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        generated_boundary = path_boundary_diagnostics(
            git_dir,
            [git_dir / "info", key_path],
            code="unsafe_signing_key_path",
        )
        try:
            generated_mode = stat.S_IMODE(key_path.lstat().st_mode)
            generated_content = key_path.read_text(encoding="utf-8").strip()
            generated_valid = (
                not key_path.is_symlink()
                and key_path.is_file()
                and generated_mode == 0o600
                and re.fullmatch(r"[0-9A-Fa-f]{64}", generated_content) is not None
            )
        except OSError:
            generated_valid = False
        if generated.returncode != 0 or generated_boundary or not generated_valid:
            return Result(
                "tasks setup-signing-key",
                "SIGNING_KEY=ERROR",
                EXIT_CONFLICT,
                root,
                diagnostics=[
                    Diagnostic(
                        "signing_key_setup_failed",
                        "The embedded Task Pack could not provision the signing key.",
                        detail={
                            "exit_code": generated.returncode,
                            "stderr": generated.stderr[-1000:],
                            "path_diagnostics": [item.as_dict() for item in generated_boundary],
                        },
                    )
                ],
            )
    return Result(
        "tasks setup-signing-key",
        "SIGNING_KEY=READY",
        EXIT_OK,
        root,
        artifacts=[key_path],
        next_steps=[
            "Run seamwise status; re-seal prior specs if this command rotated an existing key."
        ],
        data={"created": True, "dry_run": False, "rotation": force},
    )
