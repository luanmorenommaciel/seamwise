#!/usr/bin/env python3
"""Check local links, Mermaid fences, status language, and assets."""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    documents = [
        root / "README.md",
        root / "AGENTS.md",
        root / "CLAUDE.md",
        *sorted((root / "skills").glob("*/SKILL.md")),
    ]
    errors: list[str] = []
    forbidden = (
        root / "PLAN.md",
        root / "TASK_PACK_CHANGELOG.md",
        root / "TASK_PACK_VERSION",
        root / "docs/task-spec-v0.1.pdf",
        root / "examples",
        root / "skills/task-spec/references/examples",
        root / "bin",
    )
    for path in forbidden:
        if path.exists():
            errors.append(f"obsolete public artifact remains: {path}")
    for document in documents:
        text = document.read_text(encoding="utf-8")
        if text.count("```mermaid") > text.count("```") // 2:
            errors.append(f"unbalanced Mermaid fence: {document}")
        for block in re.findall(r"```mermaid\n(.*?)```", text, flags=re.DOTALL):
            first = block.strip().splitlines()[0] if block.strip() else ""
            if first not in {
                "flowchart LR",
                "flowchart TB",
                "graph LR",
                "graph TB",
                "sequenceDiagram",
            }:
                errors.append(f"unexpected Mermaid start in {document}: {first}")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"broken local link in {document}: {raw_target}")
    readme = (root / "README.md").read_text(encoding="utf-8")
    for required in (
        "seamwise init",
        "seamwise map",
        "seamwise plan",
        "seamwise review",
        "seamwise compile",
        "seamwise --json capabilities",
        "TaskPlan/v1",
        "SeamwiseTaskPlanLineage/v1",
        "install codex --scope project",
        "install claude --scope project",
        "DELIVERY_PLAN=NEEDS_REVIEW",
        "materializes_tasks: false",
    ):
        if required not in readme:
            errors.append(f"README missing required command/boundary: {required}")
    for stale in (
        "Implementation: not yet",
        "compiler and CLI | Not implemented",
        "pre-implementation foundation",
        "SEAMWISE_TASKSPEC_BIN",
        "invokes the independently installed Task-Spec",
    ):
        if stale in readme:
            errors.append(f"README retains stale foundation claim: {stale}")
    for asset in sorted((root / "assets").glob("*.svg")):
        ET.parse(asset)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Documentation valid: {len(documents)} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
