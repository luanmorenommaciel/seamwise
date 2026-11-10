from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import compile_fixture, make_link

from seamwise.io import workspace_lock
from seamwise.portability import (
    default_lock_home,
    default_state_home,
    is_link,
    supported_platform,
)

_CONTENDER = """
import sys
from pathlib import Path
from seamwise.io import workspace_lock

root, started, acquired = (Path(value) for value in sys.argv[1:4])
started.write_text("started", encoding="utf-8")
with workspace_lock(root):
    acquired.write_text("acquired", encoding="utf-8")
"""


def _wait_for(path: Path, *, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return path.exists()


def test_this_host_is_a_supported_platform() -> None:
    assert supported_platform()


def test_workspace_lock_blocks_a_second_process_until_release(tmp_path: Path) -> None:
    started = tmp_path / "contender-started"
    acquired = tmp_path / "contender-acquired"
    with workspace_lock(tmp_path):
        contender = subprocess.Popen(
            [sys.executable, "-c", _CONTENDER, str(tmp_path), str(started), str(acquired)],
            env=dict(os.environ),
        )
        try:
            assert _wait_for(started, seconds=20), "contender process never started"
            assert not _wait_for(acquired, seconds=0.5), "lock did not exclude the contender"
        except BaseException:
            contender.kill()
            raise
    assert contender.wait(timeout=20) == 0
    assert acquired.read_text(encoding="utf-8") == "acquired"


def test_workspace_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    for _ in range(3):
        with workspace_lock(tmp_path):
            pass


def test_regular_files_and_directories_are_not_links(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    regular = tmp_path / "file.txt"
    regular.write_text("content", encoding="utf-8")
    assert not is_link(directory)
    assert not is_link(regular)
    assert not is_link(tmp_path / "missing")


def test_directory_link_is_detected_on_every_platform(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    make_link(link, outside, directory=True)
    assert is_link(link)


@pytest.mark.skipif(sys.platform != "win32", reason="directory junctions exist only on Windows")
def test_windows_junction_is_a_link_that_is_symlink_misses(tmp_path: Path) -> None:
    import _winapi

    outside = tmp_path / "outside"
    outside.mkdir()
    junction = tmp_path / "junction"
    _winapi.CreateJunction(str(outside), str(junction))
    assert not junction.is_symlink()
    assert is_link(junction)


def test_default_per_user_directories_are_absolute() -> None:
    assert default_state_home().is_absolute()
    assert default_lock_home().is_absolute()


def _path_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "path" and isinstance(item, str):
                found.append(item)
            found.extend(_path_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_path_values(item))
    return found


def test_recorded_relative_paths_use_forward_slashes(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    assert compile_fixture(tmp_path, recipe).ok
    recorded: list[str] = []
    for artifact in (tmp_path / "seamwise").rglob("*.json"):
        recorded.extend(_path_values(json.loads(artifact.read_text(encoding="utf-8"))))
    assert recorded, "the compiled workspace recorded no relative paths"
    assert not [path for path in recorded if "\\" in path]


def test_json_output_survives_a_pipe_with_a_legacy_locale(tmp_path: Path) -> None:
    workspace = tmp_path / "espaço → 日本"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONIOENCODING", "PYTHONUTF8"}
    }
    environment["PYTHONUTF8"] = "0"
    completed = subprocess.run(
        [sys.executable, "-m", "seamwise.cli", "--workspace", str(workspace), "--json", "init"],
        capture_output=True,
        env=environment,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    envelope = json.loads(completed.stdout.decode("utf-8").strip().splitlines()[-1])
    assert envelope["ok"] is True
    assert "日本" in json.dumps(envelope, ensure_ascii=False)
