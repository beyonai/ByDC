.PHONY: lint test format ci-check install-hooks

format:
	uv run ruff format .

lint:
	uv run ruff check .
	uv run mypy .

ci-check:
	uv run --frozen --all-packages ruff format src/by_datacloud packages --check
	uv run --frozen --all-packages ruff check src/by_datacloud packages
	uv run --frozen --all-packages mypy src/by_datacloud packages

install-hooks:
	uv run --frozen --all-packages pre-commit install --install-hooks

test:
	uv run pytest
