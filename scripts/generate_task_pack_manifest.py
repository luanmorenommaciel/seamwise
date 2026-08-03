#!/usr/bin/env python3
"""Generate the immutable Phase-0 Task Pack provenance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("vendor/task-pack-source.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    task_pack = root / "skills" / "task-spec"
    files: dict[str, dict[str, object]] = {}
    for path in sorted(item for item in task_pack.rglob("*") if item.is_file()):
        relative = str(path.relative_to(task_pack))
        files[relative] = {
            "mode": format(stat.S_IMODE(path.stat().st_mode), "04o"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    payload = {
        "schema_version": 1,
        "source": "https://github.com/luanmorenommaciel/converge",
        "source_visibility_at_import": "private",
        "source_ref": "v0.1.0",
        "source_commit": "b585ca792418924182e1c6a87f660a5f8afa07bd",
        "source_document": {
            "included": False,
            "upstream_path": "docs/task-spec-v0.1.pdf",
            "sha256": "1737ace66228bebb131803256bfb7df633ba631fbb19bd88a8ff91520eb7f72a",
        },
        "source_tree": "95dae33bf9c8da852ae50a7b6cfc44176cdaa5c8",
        "imported_at": "2026-08-02",
        "license": "MIT",
        "destination": "skills/task-spec",
        "local_changes": [
            {
                "kind": "documentation-only",
                "path": "README.md",
                "reason": "Removed links to Task Pack package artifacts not shipped by Seamwise.",
            },
            {
                "kind": "reference-cleanup",
                "path": "references/examples",
                "reason": "Removed six illustrative Task-Specs; they are not runtime or conformance inputs.",
            },
            {
                "kind": "reference-move",
                "path": "references/consumers",
                "reason": "Moved the load-bearing cross-engine consumers out of the removed examples directory.",
            },
        ],
        "file_count": len(files),
        "files": files,
    }
    output = root / args.output
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"Task Pack manifest is stale: {output}")
        print(f"Task Pack manifest matches {len(files)} files")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output} with {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
