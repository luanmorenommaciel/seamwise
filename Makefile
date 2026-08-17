.PHONY: check check-hosts test cov lint typecheck build

check:
	./scripts/release-check.sh

check-hosts:
	uv run python scripts/host_plugin_e2e.py

test:
	uv run pytest -q

cov:
	uv run pytest -q --cov --cov-report=term-missing

lint:
	uv run ruff format --check src tests scripts
	uv run ruff check src tests scripts

typecheck:
	uv run mypy

build:
	uv build
