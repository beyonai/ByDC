# Contributing

Thanks for contributing to dataCloud.

## Basic Workflow

1. Create a feature branch.
2. Keep changes focused and testable.
3. Run lint and tests before opening PR.
4. Open a pull request with clear context.

## Standards

- Follow `docs/项目规范/CODING_CONVENTIONS.md`.
- Follow `docs/项目规范/TESTING_CONVENTIONS.md`.

## Git Hooks

To block local commits that would fail CI, install the repository pre-commit hook once.

macOS / Linux:

```bash
make install-hooks
```

Windows / cross-platform:

```bash
uv run python scripts/install_hooks.py
```

The hook runs the same core checks as CI before `git commit` succeeds:

- `uv run --frozen --all-packages ruff format src/by_datacloud packages --check`
- `uv run --frozen --all-packages ruff check src/by_datacloud packages`
- `uv run --frozen --all-packages mypy src/by_datacloud packages`

You can also run the full local CI gate manually:

```bash
make ci-check
```
