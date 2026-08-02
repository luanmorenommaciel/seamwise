#!/usr/bin/env python3
"""Run every imported Task Pack suite in a disposable parity copy."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from seamwise.taskpack import task_pack_root, verify_task_pack

SUITES = (
    "test-task-spec-skill.sh",
    "test-bash-portability.sh",
    "test-effort-sizing.sh",
    "test-extractor-fuzz.sh",
    "test-hmac-envelope.sh",
    "test-portability-e2e.sh",
    "test-v3-closed-loop-e2e.sh",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    diagnostics = verify_task_pack()
    if diagnostics:
        raise SystemExit("\n".join(item.message for item in diagnostics))
    with tempfile.TemporaryDirectory(prefix="seamwise-task-pack-") as directory:
        copied = Path(directory) / "task-spec"
        shutil.copytree(task_pack_root(), copied, copy_function=shutil.copy2)
        for suite in SUITES:
            subprocess.run(["bash", str(copied / "tests" / suite)], cwd=directory, check=True)
        runner = copied / "tests/conformance/run_conformance.sh"
        adapter = copied / "tests/conformance/adapters/self.sh"
        subprocess.run(["bash", str(runner), "--adapter", str(adapter)], cwd=directory, check=True)
    diagnostics = verify_task_pack()
    if diagnostics:
        raise SystemExit("Source Task Pack changed while running disposable suites")
    print(f"Task Pack parity suites passed: {len(SUITES)} suites plus conformance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
