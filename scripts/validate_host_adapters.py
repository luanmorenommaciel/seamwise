#!/usr/bin/env python3
"""Portable validation for the dual host manifests and shared skills."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

import yaml

SKILLS = (
    "seamwise",
    "to-seam-map",
    "to-delivery-plan",
    "to-task-graph",
    "to-task-specs",
)


def frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"missing frontmatter: {path}")
    raw, _ = text[4:].split("\n---\n", 1)
    value = yaml.safe_load(raw)
    if not isinstance(value, dict):
        raise ValueError(f"frontmatter is not a mapping: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert version, "VERSION file is empty"
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in pyproject.get("project", {}).get("dynamic", [])
    hatch_version = pyproject.get("tool", {}).get("hatch", {}).get("version", {})
    assert hatch_version.get("path") == "VERSION"
    manifests = [
        json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8")),
        json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8")),
    ]
    for manifest in manifests:
        assert manifest["name"] == "seamwise"
        assert manifest["version"] == version
        assert manifest["skills"] == "./skills/"
        assert manifest["repository"] == "https://github.com/luanmorenommaciel/seamwise"
        assert manifest["license"] == "MIT"
    codex_marketplace = json.loads(
        (root / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
    )
    assert codex_marketplace["name"] == "seamwise"
    assert codex_marketplace["plugins"] == [
        {
            "name": "seamwise",
            "source": {"source": "local", "path": "./"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Developer Tools",
        }
    ]
    claude_marketplace = json.loads(
        (root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    assert claude_marketplace["name"] == "seamwise"
    assert claude_marketplace["version"] == version
    assert claude_marketplace["plugins"][0]["source"] == "./"
    assert claude_marketplace["plugins"][0]["version"] == version
    for name in SKILLS:
        skill_path = root / "skills" / name / "SKILL.md"
        metadata = frontmatter(skill_path)
        assert set(metadata) == {"name", "description"}
        assert metadata["name"] == name
        assert isinstance(metadata["description"], str) and metadata["description"].strip()
        text = skill_path.read_text(encoding="utf-8")
        assert "seamwise --workspace" in text or name == "seamwise"
        lowered = text.lower()
        assert any(term in lowered for term in ("never", "may not", "do not"))
        assert "recipe example" not in lowered
        openai_path = root / "skills" / name / "agents" / "openai.yaml"
        openai = yaml.safe_load(openai_path.read_text(encoding="utf-8"))
        interface = openai["interface"]
        assert set(interface) == {"display_name", "short_description", "default_prompt"}
        assert f"${name}" in interface["default_prompt"]
    print(f"Host adapters valid: 2 manifests, 2 marketplaces, {len(SKILLS)} shared skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
