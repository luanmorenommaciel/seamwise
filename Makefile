.PHONY: check check-hosts test build

check:
	./scripts/release-check.sh

check-hosts:
	uv run python scripts/host_plugin_e2e.py

test:
	uv run pytest -q

build:
	uv build
