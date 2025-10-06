# Use uv

.PHONY: venv dev-deps fmt fmt-check lint typecheck test check fix

venv:
	@uv venv
	@echo "✔ Created .venv (Python 3.11+)"

dev-deps:
	@uv pip install -U ruff pytest pyright
	@echo "✔ Installed dev deps (ruff, pytest, pyright)"

fmt:
	@uv run ruff format .
	@echo "✔ Formatted (ruff format)"

fmt-check:
	@uv run ruff format --check .
	@echo "✔ Format check OK"

lint:
	@uv run ruff check .
	@echo "✔ Lint OK"

typecheck:
	@uv run pyright
	@echo "✔ Types OK"

test:
	@uv run pytest
	@echo "✔ Tests OK"

check: fmt-check lint typecheck test

fix: fmt
