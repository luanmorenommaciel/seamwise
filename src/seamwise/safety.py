"""Filesystem write-boundary checks for compiler and host-managed paths."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from seamwise.result import Diagnostic

MANAGED_WORKSPACE_DIRECTORIES = (
    "seamwise",
    "seamwise/decisions",
    "seamwise/seams",
    "seamwise/swimlanes",
    "seamwise/legs",
    "seamwise/reviews",
    "tasks",
    "telemetry",
    "reports",
    "lessons",
)
MANAGED_WORKSPACE_ROOTS = ("seamwise", "tasks", "telemetry", "reports", "lessons")


def path_boundary_diagnostics(
    base: Path,
    targets: Iterable[Path],
    *,
    code: str = "unsafe_managed_path",
) -> list[Diagnostic]:
    """Reject lexical escapes, symlink components, and non-directory ancestors."""

    base = Path(os.path.abspath(base))
    diagnostics: list[Diagnostic] = []
    if base.is_symlink():
        diagnostics.append(
            Diagnostic(
                code,
                "Authorized path base may not itself be a symlink.",
                str(base),
            )
        )
    elif base.exists() and not base.is_dir():
        diagnostics.append(
            Diagnostic(
                code,
                "Authorized path base must be a directory.",
                str(base),
            )
        )
    seen: set[Path] = set()
    for target in targets:
        target = Path(os.path.abspath(target))
        try:
            relative = target.relative_to(base)
        except ValueError:
            diagnostics.append(
                Diagnostic(
                    code,
                    "Managed path resolves outside its authorized base.",
                    str(target),
                    {"base": str(base)},
                )
            )
            continue
        current = base
        for index, part in enumerate(relative.parts):
            current /= part
            if current in seen:
                continue
            seen.add(current)
            if current.is_symlink():
                diagnostics.append(
                    Diagnostic(
                        code,
                        "Managed path contains a symlink component.",
                        str(current),
                        {"base": str(base)},
                    )
                )
                break
            if current.exists() and index < len(relative.parts) - 1 and not current.is_dir():
                diagnostics.append(
                    Diagnostic(
                        code,
                        "Managed path contains a non-directory ancestor.",
                        str(current),
                        {"base": str(base)},
                    )
                )
                break
    return diagnostics


def workspace_boundary_diagnostics(
    root: Path, *, extra_paths: Iterable[Path] = ()
) -> list[Diagnostic]:
    """Verify every managed workspace tree and any command-specific output path."""

    root = Path(os.path.abspath(root))
    managed_directories = [root / name for name in MANAGED_WORKSPACE_DIRECTORIES]
    diagnostics = path_boundary_diagnostics(root, [*managed_directories, *extra_paths])
    for directory in managed_directories:
        if directory.exists() and not directory.is_dir() and not directory.is_symlink():
            diagnostics.append(
                Diagnostic(
                    "unsafe_managed_path",
                    "A managed workspace directory slot is occupied by a non-directory.",
                    str(directory),
                    {"base": str(root)},
                )
            )
    for managed_root in (root / name for name in MANAGED_WORKSPACE_ROOTS):
        if not managed_root.is_dir() or managed_root.is_symlink():
            continue
        for current, directories, files in os.walk(managed_root, followlinks=False):
            current_path = Path(current)
            for name in [*directories, *files]:
                candidate = current_path / name
                if candidate.is_symlink():
                    diagnostics.append(
                        Diagnostic(
                            "unsafe_managed_path",
                            "Managed workspace trees may not contain symlinks.",
                            str(candidate),
                            {"base": str(root)},
                        )
                    )
            directories[:] = [
                name for name in directories if not (current_path / name).is_symlink()
            ]
    unique: dict[tuple[str, str | None], Diagnostic] = {}
    for diagnostic in diagnostics:
        unique[(diagnostic.code, diagnostic.artifact)] = diagnostic
    return list(unique.values())
