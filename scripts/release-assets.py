#!/usr/bin/env python3
"""Assemble deterministic GitHub release assets and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_project_version(root: Path) -> str:
    path = root / "VERSION"
    version = path.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit(f"empty VERSION file: {path}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--ci-run-url", required=True)
    parser.add_argument("--taskspec-version", default="3.8.0")
    parser.add_argument(
        "--taskspec-commit",
        default="0e6180cfc3009bd4ef9cf7ab050b463e10d4af91",
    )
    args = parser.parse_args()
    version = read_project_version(Path.cwd())

    artifacts = [
        args.dist / f"seamwise-{version}-py3-none-any.whl",
        args.dist / f"seamwise-{version}.tar.gz",
    ]
    missing = [path for path in artifacts if not path.is_file()]
    if missing:
        raise SystemExit(f"missing stable release artifacts: {missing}")

    args.out.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    checksum_lines: list[str] = []
    for source in artifacts:
        destination = args.out / source.name
        shutil.copyfile(source, destination)
        digest = sha256(destination)
        entries.append(
            {"name": destination.name, "sha256": digest, "bytes": destination.stat().st_size}
        )
        checksum_lines.append(f"{digest}  {destination.name}")

    manifest = {
        "contract": "SeamwiseReleaseManifest/v1",
        "product": "seamwise",
        "version": version,
        "source": {"commit": args.source_commit, "ref": args.source_ref},
        "dependencies": [
            {
                "product": "task-spec",
                "version": args.taskspec_version,
                "commit": args.taskspec_commit,
            }
        ],
        "artifacts": entries,
        "ci": {"run_url": args.ci_run_url},
    }
    (args.out / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.out / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
