.PHONY: sync test lint typecheck check explorer

sync:
	uv sync --all-extras

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy src/

check: test lint typecheck

explorer:
	uv run --extra notebook marimo edit notebooks/explorateur.py
