.PHONY: check test build

check:
	./scripts/release-check.sh

test:
	uv run pytest -q

build:
	uv build
