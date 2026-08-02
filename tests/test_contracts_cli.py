from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner
from conftest import RECIPE
from jsonschema import Draft202012Validator

from seamwise.cli import cli
from seamwise.contracts import load_schema, validate_contract
from seamwise.engine import accept_plan, build_plan, compile_graph, map_recipe
from seamwise.io import sha256_file
from seamwise.taskpack import task_pack_root
from seamwise.workspace import init_workspace

SCHEMAS = (
    "result-envelope",
    "recipe",
    "seam-map",
    "delivery-plan",
    "delivery-plan-review",
    "task-graph",
    "task-lineage",
    "task-check-receipt",
    "install-receipt",
)


def test_all_published_schemas_are_valid() -> None:
    for name in SCHEMAS:
        Draft202012Validator.check_schema(load_schema(name))


def test_recipe_rejects_malformed_freshness_and_source_locator(
    recipe: dict[str, Any],
) -> None:
    malformed = copy.deepcopy(recipe)
    malformed["intent"]["source"]["captured_at"] = "yesterday"
    malformed["evidence"][0]["source"]["uri"] = "not a URI or path"
    errors = validate_contract("recipe", malformed)
    assert any("date-time" in error for error in errors)
    assert any("not valid under any of the given schemas" in error for error in errors)


def test_recipe_source_locator_accepts_one_safe_bare_filename(
    recipe: dict[str, Any],
) -> None:
    recipe["intent"]["source"]["uri"] = "README.md"
    recipe["evidence"][0]["source"]["uri"] = "blueprint.pdf"
    assert validate_contract("recipe", recipe) == []


def test_cli_json_is_exactly_one_valid_envelope(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--workspace", str(tmp_path), "--json", "status"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert validate_contract("result-envelope", payload) == []
    assert payload["token"] == "STATUS=READY"
    assert payload["next"] == ["seamwise init"]


def test_init_is_non_clobbering(tmp_path: Path) -> None:
    assert init_workspace(tmp_path).ok
    intent = tmp_path / "seamwise/intent.md"
    original = intent.read_text(encoding="utf-8")
    second = init_workspace(tmp_path)
    assert second.token == "WORKSPACE=EXISTS"
    assert second.exit_code == 3
    assert intent.read_text(encoding="utf-8") == original


def test_compile_is_deterministic_for_authority_artifacts(
    tmp_path: Path, recipe: dict[str, Any]
) -> None:
    source = tmp_path / "recipe.yaml"
    source.write_text(yaml.safe_dump(recipe, sort_keys=False), encoding="utf-8")
    assert init_workspace(tmp_path).ok
    assert map_recipe(tmp_path, source).ok
    assert build_plan(tmp_path).exit_code == 2
    assert accept_plan(tmp_path, reviewer="pytest", reason="fixture", fixture=True).ok
    assert compile_graph(tmp_path, task_pack_root=task_pack_root()).ok
    paths = [
        tmp_path / "tasks/task-graph.yaml",
        tmp_path / "tasks/task-lineage.json",
        *sorted((tmp_path / "tasks").glob("T-*.md")),
    ]
    first = {str(path): sha256_file(path) for path in paths}
    assert compile_graph(tmp_path, task_pack_root=task_pack_root()).ok
    assert {str(path): sha256_file(path) for path in paths} == first


def test_prepare_stops_at_review_gate(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--workspace",
            str(tmp_path),
            "--json",
            "prepare",
            "--source",
            str(RECIPE),
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["token"] == "DELIVERY_PLAN=NEEDS_REVIEW"
    assert not (tmp_path / "seamwise/reviews/delivery-plan-review.json").exists()
