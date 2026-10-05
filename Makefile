.PHONY: sync test lint typecheck check explorer srd-lab srd-lab-run

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

srd-lab:
	uv run --extra notebook marimo edit notebooks/srd_research_lab.py

srd-lab-run:
	uv run --extra notebook marimo run notebooks/srd_research_lab.py
