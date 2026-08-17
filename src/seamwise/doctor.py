"""Credential-free diagnostics plus optional explicit live host probes."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from seamwise.assets import assets_root
from seamwise.constants import (
    DOCTOR_BLOCKED,
    DOCTOR_OK,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    VERSION,
)
from seamwise.contracts import validate_contract
from seamwise.installer import verify_installation
from seamwise.result import Diagnostic, Result


def _supported_platform() -> bool:
    return sys.platform.startswith("linux") or sys.platform == "darwin"


def _probe_version(executable: str) -> dict[str, Any]:
    path = shutil.which(executable)
    if path is None:
        return {"name": executable, "available": False, "path": None, "version": None}
    process = subprocess.run(
        [path, "--version"], capture_output=True, text=True, check=False, timeout=20
    )
    output = (process.stdout or process.stderr).strip().splitlines()
    return {
        "name": executable,
        "available": process.returncode == 0,
        "path": path,
        "version": output[0] if output else None,
        "exit_code": process.returncode,
    }


def _doctor_envelope(text: str) -> bool:
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and {
            "command": value.get("command"),
            "token": value.get("token"),
            "exit_code": value.get("exit_code"),
            "ok": value.get("ok"),
        } == {"command": "doctor", "token": DOCTOR_OK, "exit_code": 0, "ok": True}:
            return True
    return False


def _verified_host_tool_result(host: str, output: str) -> bool:
    try:
        events = [json.loads(line) for line in output.splitlines() if line.strip()]
    except ValueError:
        return False
    for event in events:
        if not isinstance(event, dict):
            continue
        if host == "codex":
            item = event.get("item")
            if (
                isinstance(item, dict)
                and item.get("type") == "command_execution"
                and "seamwise --json doctor --host core" in str(item.get("command", ""))
                and _doctor_envelope(str(item.get("aggregated_output", "")))
            ):
                return True
        else:
            message = event.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                if _doctor_envelope(str(block.get("content", ""))):
                    return True
    return False


def _live_probe(host: str, root: Path) -> dict[str, Any]:
    if host == "codex":
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--json",
            "$seamwise Run `seamwise --json doctor --host core` and report its final token.",
        ]
    else:
        command = [
            "claude",
            "--bare",
            "-p",
            "/seamwise Run `seamwise --json doctor --host core` and return the raw tool result.",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
    process = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    output = f"{process.stdout}\n{process.stderr}"
    return {
        "host": host,
        "command": command,
        "exit_code": process.returncode,
        "ok": process.returncode == 0 and _verified_host_tool_result(host, process.stdout),
        "output_tail": output[-4000:],
    }


def doctor(
    root: Path,
    *,
    host: str = "core",
    live: bool = False,
    scope: str = "project",
    target: Path | None = None,
) -> Result:
    checks: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    supported_platform = _supported_platform()
    checks.append(
        {
            "name": "supported_platform",
            "ok": supported_platform,
            "value": sys.platform,
            "required": True,
        }
    )
    if not supported_platform:
        diagnostics.append(
            Diagnostic(
                "unsupported_platform",
                "Seamwise requires macOS, Linux, or Linux under WSL for its file-locking model.",
            )
        )
    checks.append(
        {
            "name": "python",
            "ok": sys.version_info >= (3, 11),
            "value": ".".join(str(item) for item in sys.version_info[:3]),
            "required": True,
        }
    )
    checks.append(
        {
            "name": "seamwise_version",
            "ok": (assets_root() / "VERSION").read_text(encoding="utf-8").strip() == VERSION,
            "value": VERSION,
            "required": True,
        }
    )
    sample_envelope = {
        "contract": "SeamwiseCLIResult/v1",
        "engine_version": VERSION,
        "schema_version": 1,
        "command": "doctor",
        "ok": True,
        "token": DOCTOR_OK,
        "exit_code": 0,
        "workspace": str(root),
        "artifacts": [],
        "diagnostics": [],
        "next": [],
    }
    schema_errors = validate_contract("result-envelope", sample_envelope)
    checks.append(
        {
            "name": "result_envelope_schema",
            "ok": not schema_errors,
            "value": schema_errors,
            "required": True,
        }
    )
    for executable in ("git",):
        probe = _probe_version(executable)
        checks.append({**probe, "ok": probe["available"], "required": True})
    required_hosts = () if host == "core" else (("codex", "claude") if host == "all" else (host,))
    host_probes: dict[str, dict[str, Any]] = {}
    for current in ("codex", "claude"):
        probe = _probe_version(current)
        host_probes[current] = probe
        checks.append({**probe, "ok": probe["available"], "required": current in required_hosts})
    if required_hosts:
        install_checks, install_diagnostics = verify_installation(
            root, host=host, scope=scope, target=target
        )
        checks.extend({**item, "required": True} for item in install_checks)
        diagnostics.extend(install_diagnostics)
    live_probes: list[dict[str, Any]] = []
    live_root = (
        target.expanduser().resolve()
        if target is not None
        else root.resolve()
        if scope == "project"
        else Path.home().resolve()
    )
    if live:
        for current in required_hosts:
            if host_probes[current]["available"]:
                try:
                    probe = _live_probe(current, live_root)
                except subprocess.TimeoutExpired as error:
                    probe = {
                        "host": current,
                        "ok": False,
                        "exit_code": None,
                        "output_tail": f"Timed out after {error.timeout} seconds",
                    }
                live_probes.append(probe)
                checks.append(
                    {
                        "name": f"{current}_live",
                        "ok": probe["ok"],
                        "required": True,
                        "value": probe["output_tail"],
                    }
                )
    failures = [item for item in checks if item["required"] and not item["ok"]]
    if diagnostics:
        failures.append({"name": "contract_boundary", "ok": False, "required": True})
    for failure in failures:
        if failure["name"] == "supported_platform":
            continue
        diagnostics.append(
            Diagnostic("doctor_check_failed", f"Required check failed: {failure['name']}")
        )
    token = DOCTOR_OK if not failures else DOCTOR_BLOCKED
    return Result(
        "doctor",
        token,
        EXIT_OK if not failures else EXIT_UNAVAILABLE,
        root,
        diagnostics=diagnostics,
        next_steps=[] if not failures else ["Resolve the named required checks and rerun doctor."],
        data={"checks": checks, "live_probes": live_probes, "live": live},
    )
