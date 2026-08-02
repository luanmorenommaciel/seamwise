from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from seamwise.engine import accept_plan, build_plan, compile_graph, map_recipe
from seamwise.taskpack import task_pack_root
from seamwise.workspace import init_workspace

REPOSITORY = Path(__file__).resolve().parents[1]
RECIPE = REPOSITORY / "examples" / "rate-limiting" / "recipe.yaml"


@pytest.fixture(autouse=True)
def isolated_seamwise_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEAMWISE_STATE_HOME", str(tmp_path / ".runtime-state"))


@pytest.fixture
def recipe() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(RECIPE.read_text(encoding="utf-8")))


def write_recipe(root: Path, value: dict[str, Any]) -> Path:
    path = root / "recipe.yaml"
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    return path


def git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)


def compile_fixture(root: Path, value: dict[str, Any]):  # type: ignore[no-untyped-def]
    git_init(root)
    source = write_recipe(root, value)
    assert init_workspace(root).ok
    assert map_recipe(root, source).ok
    plan = build_plan(root)
    assert plan.token == "DELIVERY_PLAN=NEEDS_REVIEW"
    assert accept_plan(root, reviewer="pytest", reason="fixture review", fixture=True).ok
    return compile_graph(root, task_pack_root=task_pack_root())
