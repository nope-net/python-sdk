# NOPE Python SDK developer targets. Every offline target is what CI runs.

.PHONY: install lint format typecheck test check build generate live live-smoke clean

install:
	pip install -e '.[dev]'

lint:
	ruff check src tests scripts
	ruff format --check src tests scripts

format:
	ruff format src tests scripts
	ruff check --fix src tests scripts

typecheck:
	mypy src tests/typing

# Unit + contract tests; the live suite is excluded by pyproject addopts.
test:
	pytest

check: lint typecheck test

build:
	rm -rf dist
	python -m build

# Regenerate the Literal enums from the sibling ../api checkout.
generate:
	python scripts/generate_taxonomy.py

# Live suite: calls api.nope.net and spends balance. Key from NOPE_E2E_API_KEY,
# else NOPE_DEDICATED_CI_KEY in ../api/.env. Serial by design.
live:
	NOPE_LIVE=1 pytest -m live tests/live

live-smoke:
	NOPE_LIVE=1 SMOKE=1 pytest -m live tests/live

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
