#!/usr/bin/env python3
"""Prove the built wheel in an isolated venv and disposable workspaces.

The authored proving fixture deliberately retains its host-tool contract:
``shellcheck`` and ``pytest`` must already be available on ``PATH``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
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
    missing_host_tools = [
        tool for tool in ("git", "bash", "shellcheck", "pytest") if shutil.which(tool) is None
    ]
    if missing_host_tools:
        raise RuntimeError(
            "clean-room proving fixture requires host tools on PATH: "
            + ", ".join(missing_host_tools)
        )
    with tempfile.TemporaryDirectory(prefix="seamwise-clean-room-") as directory:
        clean = Path(directory)
        os.environ["SEAMWISE_STATE_HOME"] = str(clean / "runtime-state")
        venv = clean / "venv"
        run(["uv", "venv", str(venv)])
        python = venv / "bin/python"
        run(["uv", "pip", "install", "--python", str(python), str(wheel)])
        seamwise = venv / "bin/seamwise"
        task_spec = venv / "bin/task-spec"
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
        assert (
            envelope(
                seamwise,
                workspace,
                ["recipe", "example", "--output", str(recipe)],
            )["token"]
            == "RECIPE_EXAMPLE=READY"
        )
        recipe_text = recipe.read_text(encoding="utf-8")
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
        blueprint = workspace / "seamwise-evidence/seamwise.pdf"
        assert hashlib.sha256(blueprint.read_bytes()).hexdigest() == (
            "cad353a000ee1cffe5c41e56307c4d1ac164641853d21f78cbc90d8c8271e5ee"
        )
        pre_map_packet = envelope(seamwise, workspace, ["agent-context", "--host", "chat"])
        assert "recipe_authoring" in str(pre_map_packet["data"]["packet"])
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
        assert envelope(seamwise, workspace, ["compile"])["token"] == "TASK_GRAPH=READY"
        assert envelope(seamwise, workspace, ["tasks", "validate"])["token"] == "TASK_SPECS=VALID"
        assert (
            envelope(
                seamwise,
                workspace,
                ["tasks", "preflight", "--acknowledge-eval-execution"],
            )["token"]
            == "TASK_SPECS=PREFLIGHT_READY"
        )
        for spec in (workspace / "tasks").glob("T-*.md"):
            text = spec.read_text(encoding="utf-8")
            assert "signed_off: false" in text
            assert "accepted: false" in text
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
        assert "task-spec, version 0.1.0" in run([str(task_spec), "--version"])
    print(
        "Clean-room wheel E2E passed with declared host tools: "
        "compile, validate, preflight, install, reinstall, uninstall"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
