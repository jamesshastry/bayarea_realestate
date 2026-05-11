.PHONY: install test typecheck lint format ingest status clean

# ── Bootstrap ──────────────────────────────────────────────────────────
install:
	uv sync --all-packages

# ── Quality gates ──────────────────────────────────────────────────────
test:
	uv run pytest

test-fast:
	uv run pytest -m "not integration"

typecheck:
	uv run pyright

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix .

# ── Phase 0 commands ───────────────────────────────────────────────────
# Run the Redfin CSV adapter once and write data/YYYY-MM-DD.json
ingest:
	uv run python -m adapters.cli redfin --week current

# Regenerate the static status page from data/sources.json. Pass explicit
# paths so the install-vs-repo path layout doesn't confuse the resolver.
status:
	uv run python -m observability.status_page \
		--sources data/sources.json \
		--output status/index.html

# ── Cleanup ────────────────────────────────────────────────────────────
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
