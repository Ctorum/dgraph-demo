.PHONY: install run dev test lint format check

install:
	uv sync

run:
	uv run python -m app.main

dev:
	uv run uvicorn --reload app.main:app --host 0.0.0.0 --port 28000

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check:
	uv run ruff check --fix . && uv run ruff format .
