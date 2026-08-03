#!/usr/bin/env bash
set -euo pipefail

release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$release_root"

command -v uv >/dev/null 2>&1 || { echo "RELEASE=BLOCKED — uv is required" >&2; exit 5; }
command -v shellcheck >/dev/null 2>&1 || { echo "RELEASE=BLOCKED — shellcheck is required" >&2; exit 5; }

uv sync --extra dev --locked
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy src/seamwise
uv run pytest -q
uv run python scripts/generate_task_pack_manifest.py --check
uv run python scripts/validate_host_adapters.py
uv run python scripts/validate_docs.py
uv run python scripts/run_task_pack_suites.py
uv build
release_wheel="$release_root/dist/seamwise-0.1.0-py3-none-any.whl"
test -f "$release_wheel"
uv run python scripts/clean_room_e2e.py "$release_wheel"
uv run python scripts/host_plugin_e2e.py
uv run seamwise --json doctor --host core
git diff --check
git diff --cached --check

echo "RELEASE=READY"
