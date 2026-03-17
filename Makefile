.PHONY: lint test format

format:
	uv run ruff format .

lint:
	uv run ruff check .
	uv run mypy .

test:
	uv run pytest
