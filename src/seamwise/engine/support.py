"""Leaf helpers shared by every Seamwise transformation stage."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from seamwise.io import (
    TransactionWriter,
)
from seamwise.result import Diagnostic


def _diag(code: str, message: str, artifact: Path | None = None, **detail: Any) -> Diagnostic:
    return Diagnostic(code, message, str(artifact) if artifact else None, detail)


def _duplicates(values: list[str]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return sorted(key for key, count in counts.items() if count > 1)


def _canonical_project_path(value: str) -> str | None:
    """Return one portable project-relative spelling, or reject the path."""

    if "\\" in value or value.startswith("/") or any(char in value for char in "*?[]{}"):
        return None
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        return None
    return path.as_posix()


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _event(
    writer: TransactionWriter, root: Path, stage: str, token: str, **attributes: Any
) -> None:
    path = root / "telemetry" / "events.jsonl"
    existing: list[dict[str, Any]] = []
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    import json

                    value = json.loads(line)
                    if isinstance(value, dict):
                        existing.append(value)
        except (OSError, ValueError):
            existing = []
            attributes["prior_telemetry_invalid"] = True
    existing.append(
        {
            "schema_version": 1,
            "time": dt.datetime.now(dt.UTC).isoformat(),
            "event": f"seamwise.{stage}",
            "token": token,
            "attributes": attributes,
            "authorization": False,
        }
    )
    writer.jsonl(path, existing)
