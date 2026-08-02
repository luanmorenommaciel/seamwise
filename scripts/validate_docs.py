#!/usr/bin/env python3
"""Check local links, Mermaid fences, status language, assets, and blueprint hash."""

from __future__ import annotations

import argparse
import hashlib
import json
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
        root / "PLAN.md",
        root / "docs/project.md",
        *sorted((root / "docs/decisions").glob("*.md")),
        *sorted((root / "examples").glob("**/*.md")),
    ]
    errors: list[str] = []
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
        "seamwise tasks validate",
        "install codex --scope project",
        "install claude --scope project",
        "DELIVERY_PLAN=NEEDS_REVIEW",
        "signed_off: false",
    ):
        if required not in readme:
            errors.append(f"README missing required command/boundary: {required}")
    for stale in (
        "Implementation: not yet",
        "compiler and CLI | Not implemented",
        "pre-implementation foundation",
    ):
        if stale in readme:
            errors.append(f"README retains stale foundation claim: {stale}")
    pdf = root / "docs/seamwise.pdf"
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    expected = "cad353a000ee1cffe5c41e56307c4d1ac164641853d21f78cbc90d8c8271e5ee"
    if digest != expected:
        errors.append(f"canonical blueprint changed: {digest}")
    task_pack_pdf = root / "docs/task-spec-v0.1.pdf"
    provenance = json.loads((root / "vendor/task-pack-source.json").read_text(encoding="utf-8"))
    task_pack_digest = hashlib.sha256(task_pack_pdf.read_bytes()).hexdigest()
    if task_pack_digest != provenance["source_document"]["sha256"]:
        errors.append(f"Task Pack PDF changed: {task_pack_digest}")
    for asset in sorted((root / "assets").glob("*.svg")):
        ET.parse(asset)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Documentation valid: {len(documents)} Markdown files, canonical PDF {digest[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
