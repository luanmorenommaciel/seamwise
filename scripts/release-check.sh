#!/usr/bin/env bash
set -euo pipefail

release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$release_root"

command -v uv >/dev/null 2>&1 || { echo "RELEASE=BLOCKED — uv is required" >&2; exit 5; }

uv sync --extra dev --locked
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy src/seamwise
uv run pytest -q
uv run python scripts/validate_host_adapters.py
uv run python scripts/validate_docs.py
uv build
release_wheel="$release_root/dist/seamwise-0.2.0-py3-none-any.whl"
test -f "$release_wheel"
release_assets="$(mktemp -d -t seamwise-release-assets.XXXXXX)"
trap 'rm -rf "$release_assets"' EXIT
uv run python scripts/release-assets.py \
  --dist "$release_root/dist" \
  --out "$release_assets" \
  --source-commit "$(git rev-parse HEAD)" \
  --source-ref "local-check" \
  --ci-run-url "local://release-check"
test -f "$release_assets/SHA256SUMS"
test -f "$release_assets/release-manifest.json"
uv run python scripts/clean_room_e2e.py "$release_wheel"
uv run python scripts/host_plugin_e2e.py
uv run seamwise --json doctor --host core
git diff --check
git diff --cached --check

echo "RELEASE=READY"
