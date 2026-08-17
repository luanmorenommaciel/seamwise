"""Locate Seamwise-owned package assets in source and installed layouts."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

SEAMWISE_SKILLS = (
    "seamwise",
    "to-seam-map",
    "to-delivery-plan",
    "to-task-graph",
    "to-task-specs",
)


def source_repository_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file() and (
        candidate / "skills/seamwise/SKILL.md"
    ).is_file():
        return candidate
    return None


def assets_root() -> Path:
    source = source_repository_root()
    if source is not None:
        return source
    resource = importlib.resources.files("seamwise").joinpath("assets")
    return Path(str(resource))


def skills_root() -> Path:
    return assets_root() / "skills"
