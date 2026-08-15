"""One stable command-result envelope for humans and automation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from seamwise.constants import ENVELOPE_VERSION, VERSION


@dataclass(slots=True)
class Diagnostic:
    code: str
    message: str
    artifact: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.artifact is not None:
            value["artifact"] = self.artifact
        if self.detail:
            value["detail"] = self.detail
        return value


@dataclass(slots=True)
class Result:
    command: str
    token: str
    exit_code: int
    workspace: Path
    artifacts: list[Path] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def as_dict(self) -> dict[str, Any]:
        artifacts = list(dict.fromkeys(str(path.resolve()) for path in self.artifacts))
        payload: dict[str, Any] = {
            "contract": "SeamwiseCLIResult/v1",
            "engine_version": VERSION,
            "schema_version": ENVELOPE_VERSION,
            "command": self.command,
            "ok": self.ok,
            "token": self.token,
            "exit_code": self.exit_code,
            "workspace": str(self.workspace.resolve()),
            "artifacts": artifacts,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "next": self.next_steps,
        }
        if self.data:
            payload["data"] = self.data
        return payload

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)
