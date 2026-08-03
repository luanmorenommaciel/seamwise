#!/usr/bin/env python3
"""Minimal Task-Spec v2.1.1 consumer.

Parses a T-*.md file, validates the YAML frontmatter against the published
JSON Schema, extracts the validation_card block (agent_contract + retry_policy
+ success_criteria), enumerates eval_N() bash blocks, and prints a structured
TaskSpec dataclass.

Runtime: Python 3.8+. Third-party deps: PyYAML (always), jsonschema (optional;
skipped with a warning if not installed). Schemas are resolved relative to
this file: ../schemas/task-spec-frontmatter.schema.json.

Usage:
    python3 consume-task-spec.py <path/to/T-*.md>

Exit codes:
    0 — parsed and validated cleanly
    1 — file missing / unreadable / frontmatter malformed
    2 — schema validation failed
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
FRONTMATTER_SCHEMA = SCHEMAS_DIR / "task-spec-frontmatter.schema.json"
CONTRACT_SCHEMA = SCHEMAS_DIR / "agent-contract.schema.json"

EVAL_FN_RE = re.compile(r"^(eval_\d+)\s*\(\)\s*\{", re.MULTILINE)


class _StrTimestampLoader(yaml.SafeLoader):
    """SafeLoader variant that keeps ISO timestamps as strings.

    PyYAML's default SafeLoader converts ``2026-06-02T00:00:00Z`` to a
    ``datetime`` object, which breaks JSON Schema string validation.
    """


_StrTimestampLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


def _yaml_load(text: str) -> Any:
    return yaml.load(text, Loader=_StrTimestampLoader)


@dataclass
class TaskSpec:
    """Parsed view of a Task-Spec v2.1.1 file."""

    path: str
    id: str
    title: str
    status: str
    format_version: Any
    execution_backend: str
    signed_off: bool
    frontmatter: Dict[str, Any]
    validation_card: Dict[str, Any] = field(default_factory=dict)
    eval_ids: List[str] = field(default_factory=list)


def _split_frontmatter(text: str) -> (Dict[str, Any], str):
    if not text.startswith("---"):
        raise ValueError("file does not start with YAML frontmatter '---'")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError("frontmatter not terminated by a closing '---' line")
    return _yaml_load(parts[1]) or {}, parts[2]


def _extract_validation_card(body: str) -> Dict[str, Any]:
    marker = "## Validation Card"
    idx = body.find(marker)
    if idx == -1:
        return {}
    after = body[idx + len(marker):]
    fence = after.find("```yaml")
    if fence == -1:
        return {}
    after = after[fence + len("```yaml"):]
    end = after.find("```")
    if end == -1:
        return {}
    return _yaml_load(after[:end]) or {}


def _extract_eval_ids(body: str) -> List[str]:
    marker = "## Success Criteria"
    idx = body.find(marker)
    if idx == -1:
        return []
    after = body[idx + len(marker):]
    end = after.find("\n## ")
    block = after if end == -1 else after[:end]
    return [m.group(1) for m in EVAL_FN_RE.finditer(block)]


def _validate(instance: Dict[str, Any], schema_path: Path, label: str) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        if os.environ.get("TASK_SPEC_REQUIRE_JSONSCHEMA") == "1":
            print(
                f"ERROR: jsonschema is required to validate {label} "
                "when TASK_SPEC_REQUIRE_JSONSCHEMA=1",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"WARN: jsonschema not installed; skipping {label} validation", file=sys.stderr)
        return
    with schema_path.open() as f:
        schema = json.load(f)
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: e.path)
    if errors:
        for e in errors:
            print(f"FAIL {label}: {'/'.join(str(p) for p in e.path) or '(root)'} — {e.message}", file=sys.stderr)
        sys.exit(2)


def parse(path: Path) -> TaskSpec:
    text = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    card = _extract_validation_card(body)
    eval_ids = _extract_eval_ids(body)
    _validate(fm, FRONTMATTER_SCHEMA, "frontmatter")
    if card:
        _validate(card, CONTRACT_SCHEMA, "validation_card")
    return TaskSpec(
        path=str(path),
        id=str(fm.get("id", "")),
        title=str(fm.get("title", "")),
        status=str(fm.get("status", "")),
        format_version=fm.get("format_version"),
        execution_backend=str(fm.get("execution_backend", "")),
        signed_off=bool(fm.get("signed_off", False)),
        frontmatter=fm,
        validation_card=card,
        eval_ids=eval_ids,
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: consume-task-spec.py <path/to/T-*.md>", file=sys.stderr)
        return 1
    target = Path(args[0])
    if not target.is_file():
        print(f"ERROR: {target} not found", file=sys.stderr)
        return 1
    spec = parse(target)
    summary = asdict(spec)
    summary["frontmatter"] = {k: spec.frontmatter.get(k) for k in ("id", "status", "format_version", "execution_backend", "signed_off")}
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
