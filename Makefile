.PHONY: sync test lint typecheck check

sync:
	uv sync --all-extras

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy src/

check: test lint typecheck
