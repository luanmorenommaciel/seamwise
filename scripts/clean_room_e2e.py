#!/usr/bin/env python3
"""Prove the wheel and its emitted TaskPlan against an independent Task-Spec CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


def run(command: list[str], *, expected: int = 0, cwd: Path | None = None) -> str:
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if process.returncode != expected:
        raise RuntimeError(
            f"expected {expected}, got {process.returncode}: {' '.join(command)}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
    return process.stdout


def envelope(
    seamwise: Path, workspace: Path, arguments: list[str], *, expected: int = 0
) -> dict[str, object]:
    output = run(
        [str(seamwise), "--workspace", str(workspace), "--json", *arguments],
        expected=expected,
        cwd=workspace,
    )
    lines = output.strip().splitlines()
    if len(lines) != 1:
        raise RuntimeError(f"expected one JSON envelope, got {len(lines)} lines: {output}")
    return json.loads(lines[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    root = args.root.resolve()
    with zipfile.ZipFile(wheel) as archive:
        packaged = archive.namelist()
    forbidden_package_paths = (
        "/examples/",
        "/TASK_PACK_VERSION",
        "/TASK_PACK_CHANGELOG.md",
        "/task-spec-v0.1.pdf",
        "/skills/task-spec/",
        "/vendor/",
        "/taskpack.py",
        "/task_spec_cli.py",
    )
    for forbidden in forbidden_package_paths:
        if any(forbidden in f"/{name}" for name in packaged):
            raise RuntimeError(f"wheel retains obsolete package content: {forbidden}")
    taskspec_source = os.environ.get("TASKSPEC_BIN") or shutil.which("taskspec")
    missing_host_tools = [tool for tool in ("git",) if shutil.which(tool) is None]
    if taskspec_source is None:
        missing_host_tools.append("taskspec")
    if missing_host_tools:
        raise RuntimeError(
            "clean-room proving fixture requires host tools on PATH: "
            + ", ".join(missing_host_tools)
        )
    with tempfile.TemporaryDirectory(prefix="seamwise-clean-room-") as directory:
        clean = Path(directory)
        os.environ["SEAMWISE_STATE_HOME"] = str(clean / "runtime-state")
        os.environ["SEAMWISE_LOCK_HOME"] = str(clean / "runtime-locks")
        assert taskspec_source is not None
        taskspec = str(Path(taskspec_source).resolve())
        taskspec_version = run([taskspec, "version"]).strip()
        if taskspec_version != "3.8.0":
            raise RuntimeError(
                "clean-room proving fixture requires Task-Spec 3.8.0, got "
                f"{taskspec_version or '<empty>'}"
            )
        venv = clean / "venv"
        run(["uv", "venv", str(venv)])
        python = venv / "bin/python"
        run(["uv", "pip", "install", "--python", str(python), str(wheel)])
        seamwise = venv / "bin/seamwise"
        assert not (venv / "bin/task-spec").exists()
        workspace = clean / "workspace"
        consumer = clean / "consumer"
        run(["git", "init", "-q", str(workspace)])
        assert envelope(seamwise, workspace, ["doctor", "--host", "core"])["token"] == "DOCTOR=OK"
        assert envelope(seamwise, workspace, ["init"])["token"] == "WORKSPACE=READY"
        hostile_schema = workspace / "schemas/recipe.schema.json"
        hostile_schema.parent.mkdir(parents=True)
        hostile_schema.write_text(
            '{"$schema":"https://json-schema.org/draft/2020-12/schema",'
            '"$id":"https://evil.invalid/shadow.json","type":"object"}\n',
            encoding="utf-8",
        )
        schema = envelope(seamwise, workspace, ["recipe", "schema"])
        published_schema = json.loads(str(schema["data"]["schema"]))
        assert published_schema["$id"] == ("https://seamwise.dev/schemas/recipe-v1.json")
        assert '"format": "date-time"' in str(schema["data"]["schema"])
        recipe = workspace / "recipe.yaml"
        recipe_text = (root / "tests/fixtures/rate-limiting-recipe.yaml").read_text(
            encoding="utf-8"
        )
        recipe_text = recipe_text.replace(
            "uri: docs/seamwise.pdf", "uri: seamwise-evidence/seamwise.pdf"
        )
        recipe.write_text(recipe_text, encoding="utf-8")
        blueprint = workspace / "seamwise-evidence/seamwise.pdf"
        blueprint.parent.mkdir(parents=True)
        shutil.copyfile(root / "docs/seamwise.pdf", blueprint)
        assert "uri: seamwise-evidence/seamwise.pdf" in recipe_text
        remote_recipe = workspace / "remote-recipe.yaml"
        remote_recipe.write_text(
            recipe_text.replace(
                "uri: seamwise-evidence/seamwise.pdf",
                "uri: https://example.invalid/unverified-blueprint.pdf",
                1,
            ),
            encoding="utf-8",
        )
        remote = envelope(
            seamwise,
            workspace,
            ["map", "--source", str(remote_recipe)],
            expected=2,
        )
        assert remote["diagnostics"][0]["code"] == "remote_source_unverified"
        assert hashlib.sha256(blueprint.read_bytes()).hexdigest() == (
            "cad353a000ee1cffe5c41e56307c4d1ac164641853d21f78cbc90d8c8271e5ee"
        )
        pre_map_packet = envelope(seamwise, workspace, ["agent-context", "--host", "chat"])
        assert "recipe_authoring" in str(pre_map_packet["data"]["packet"])
        assert "guided-one-pass" in str(pre_map_packet["data"]["packet"])
        assert "example_yaml" not in str(pre_map_packet["data"]["packet"])
        blueprint_bytes = blueprint.read_bytes()
        blueprint.write_bytes(b"tampered blueprint")
        tampered = envelope(
            seamwise,
            workspace,
            ["map", "--source", str(recipe)],
            expected=4,
        )
        assert tampered["diagnostics"][0]["code"] == "local_source_hash_mismatch"
        blueprint.unlink()
        missing = envelope(
            seamwise,
            workspace,
            ["map", "--source", str(recipe)],
            expected=2,
        )
        assert missing["diagnostics"][0]["code"] == "local_source_unavailable"
        blueprint.parent.mkdir(parents=True, exist_ok=True)
        blueprint.write_bytes(blueprint_bytes)
        assert (
            envelope(seamwise, workspace, ["map", "--source", str(recipe)])["token"]
            == "SEAM_MAP=READY"
        )
        assert (
            envelope(seamwise, workspace, ["plan"], expected=2)["token"]
            == "DELIVERY_PLAN=NEEDS_REVIEW"
        )
        assert (
            envelope(
                seamwise,
                workspace,
                [
                    "review",
                    "--accept",
                    "--reviewer",
                    "clean-room",
                    "--reason",
                    "wheel proving fixture",
                    "--fixture",
                ],
            )["token"]
            == "DELIVERY_PLAN=READY"
        )
        compiled = envelope(seamwise, workspace, ["compile"])
        assert compiled["token"] == "TASK_GRAPH=READY"
        compiled_artifacts = {
            Path(path).resolve().relative_to(workspace.resolve()).as_posix()
            for path in compiled["artifacts"]
        }
        assert compiled_artifacts == {
            "seamwise/task-plan.json",
            "seamwise/task-plan-lineage.json",
        }
        task_plan_path = workspace / "seamwise/task-plan.json"
        task_plan_result = json.loads(
            run(
                [taskspec, "--json", "plan", "--manifest", str(task_plan_path)],
                cwd=workspace,
            )
        )
        assert task_plan_result["contract"] == "TaskSpecCLIResult/v1"
        assert task_plan_result["data"]["contract"] == "TaskPlan/v1"
        status = envelope(seamwise, workspace, ["status"])
        assert status["data"]["task_plan"] is True
        assert status["data"]["task_plan_lineage"] is True
        assert status["data"]["materialization_receipt"] is False
        assert status["data"]["task_specs"] == 0
        assert status["data"]["dispatch_authorized"] is False
        assert "composition coordinator" in status["next"][0]
        assert not (workspace / "tasks").exists()
        assert (
            envelope(seamwise, workspace, ["agent-context", "--host", "chat"])["token"]
            == "AGENT_CONTEXT=READY"
        )
        assert (
            envelope(seamwise, workspace, ["report", "--format", "html"])["token"] == "REPORT=READY"
        )
        assert (
            envelope(
                seamwise,
                workspace,
                ["install", "all", "--scope", "project", "--target", str(consumer)],
            )["token"]
            == "INSTALL=OK"
        )
        for host in ("codex", "claude"):
            assert (
                envelope(
                    seamwise,
                    workspace,
                    [
                        "doctor",
                        "--host",
                        host,
                        "--scope",
                        "project",
                        "--target",
                        str(consumer),
                    ],
                )["token"]
                == "DOCTOR=OK"
            )
        assert (
            envelope(
                seamwise,
                workspace,
                ["install", "all", "--scope", "project", "--target", str(consumer)],
            )["token"]
            == "INSTALL=OK"
        )
        assert (
            envelope(
                seamwise,
                workspace,
                ["uninstall", "all", "--scope", "project", "--target", str(consumer)],
            )["token"]
            == "UNINSTALL=OK"
        )
    print(
        "Clean-room wheel E2E passed: two-artifact compile, independent Task-Spec "
        "TaskPlan validation, install, reinstall, uninstall"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
