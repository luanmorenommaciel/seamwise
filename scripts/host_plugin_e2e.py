#!/usr/bin/env python3
"""Exercise real Codex and Claude plugin lifecycle commands in isolated homes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(command: list[str], *, environment: dict[str, str]) -> str:
    process = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"command failed ({process.returncode}): {' '.join(command)}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
    return process.stdout


def assert_installed_copy(path: Path, manifest: str) -> None:
    if not (path / manifest).is_file():
        raise RuntimeError(f"installed plugin is missing {manifest}: {path}")
    if not (path / "skills/seamwise/SKILL.md").is_file():
        raise RuntimeError(f"installed plugin is missing the Seamwise skill: {path}")


def prove_codex(root: Path, isolated: Path) -> None:
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(isolated / "codex-home")
    Path(environment["CODEX_HOME"]).mkdir(parents=True)
    added = json.loads(
        run(["codex", "plugin", "marketplace", "add", str(root), "--json"], environment=environment)
    )
    if added["marketplaceName"] != "seamwise":
        raise RuntimeError(f"unexpected Codex marketplace result: {added}")
    installed = json.loads(
        run(["codex", "plugin", "add", "seamwise@seamwise", "--json"], environment=environment)
    )
    assert_installed_copy(Path(installed["installedPath"]), ".codex-plugin/plugin.json")
    listing = json.loads(
        run(["codex", "plugin", "list", "--available", "--json"], environment=environment)
    )
    matches = [item for item in listing["installed"] if item["pluginId"] == "seamwise@seamwise"]
    if len(matches) != 1 or not matches[0]["enabled"]:
        raise RuntimeError(f"Codex did not report one enabled Seamwise plugin: {listing}")
    run(["codex", "plugin", "remove", "seamwise@seamwise", "--json"], environment=environment)
    run(["codex", "plugin", "marketplace", "remove", "seamwise", "--json"], environment=environment)
    after = json.loads(run(["codex", "plugin", "list", "--json"], environment=environment))
    if after["installed"]:
        raise RuntimeError(f"Codex plugin uninstall left installed entries: {after}")


def prove_claude(root: Path, isolated: Path) -> None:
    environment = os.environ.copy()
    environment["CLAUDE_CONFIG_DIR"] = str(isolated / "claude-home")
    Path(environment["CLAUDE_CONFIG_DIR"]).mkdir(parents=True)
    run(
        ["claude", "plugin", "marketplace", "add", str(root), "--scope", "user"],
        environment=environment,
    )
    run(
        ["claude", "plugin", "install", "seamwise@seamwise", "--scope", "user"],
        environment=environment,
    )
    listing = json.loads(
        run(["claude", "plugin", "list", "--available", "--json"], environment=environment)
    )
    matches = [item for item in listing["installed"] if item["id"] == "seamwise@seamwise"]
    if len(matches) != 1 or not matches[0]["enabled"]:
        raise RuntimeError(f"Claude did not report one enabled Seamwise plugin: {listing}")
    assert_installed_copy(Path(matches[0]["installPath"]), ".claude-plugin/plugin.json")
    run(
        ["claude", "plugin", "uninstall", "seamwise@seamwise", "--scope", "user", "--yes"],
        environment=environment,
    )
    run(
        ["claude", "plugin", "marketplace", "remove", "seamwise", "--scope", "user"],
        environment=environment,
    )
    after = json.loads(run(["claude", "plugin", "list", "--json"], environment=environment))
    remaining = after["installed"] if isinstance(after, dict) else after
    if remaining:
        raise RuntimeError(f"Claude plugin uninstall left installed entries: {after}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    missing = [host for host in ("codex", "claude") if shutil.which(host) is None]
    if missing:
        raise RuntimeError("required host CLI is unavailable: " + ", ".join(missing))
    with tempfile.TemporaryDirectory(prefix="seamwise-host-plugin-") as directory:
        isolated = Path(directory)
        prove_codex(root, isolated)
        prove_claude(root, isolated)
    print("HOST_PLUGIN_E2E=READY — Codex and Claude install/list/uninstall passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
