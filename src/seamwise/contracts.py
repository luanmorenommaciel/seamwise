"""Load and validate versioned Seamwise JSON Schemas."""

from __future__ import annotations

import datetime as dt
import importlib.resources
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

FORMAT_CHECKER = FormatChecker()
RFC3339 = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


@FORMAT_CHECKER.checks("date-time")
def _is_rfc3339(value: object) -> bool:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        return False
    try:
        parsed = dt.datetime.fromisoformat(
            value.removesuffix("Z") + ("+00:00" if value.endswith("Z") else "")
        )
    except ValueError:
        return False
    return parsed.tzinfo is not None


@FORMAT_CHECKER.checks("uri")
def _is_explicit_uri(value: object) -> bool:
    if not isinstance(value, str) or any(character.isspace() for character in value):
        return False
    parsed = urlsplit(value)
    if not parsed.scheme:
        return False
    if parsed.scheme in {"http", "https"}:
        return bool(parsed.netloc)
    if parsed.scheme == "file":
        return bool(parsed.path)
    return bool(parsed.path or parsed.netloc)


def source_repository_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    source_file = candidate / "src" / "seamwise" / "contracts.py"
    if (
        (candidate / "pyproject.toml").is_file()
        and source_file.is_file()
        and source_file.resolve() == Path(__file__).resolve()
    ):
        return candidate
    return None


def schema_path(name: str) -> Path:
    source_root = source_repository_root()
    if source_root is not None:
        candidate = source_root / "schemas" / f"{name}.schema.json"
        if candidate.is_file():
            return candidate
    packaged = importlib.resources.files("seamwise").joinpath("schemas", f"{name}.schema.json")
    path = Path(str(packaged))
    if not path.is_file():
        raise FileNotFoundError(f"packaged Seamwise schema is unavailable: {name}")
    return path


def load_schema(name: str) -> dict[str, Any]:
    path = schema_path(name)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"schema is not an object: {path}")
    return value


def validate_contract(name: str, value: Any) -> list[str]:
    validator = Draft202012Validator(load_schema(name), format_checker=FORMAT_CHECKER)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path)):
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        errors.append(f"{location}: {error.message}")
    return errors
