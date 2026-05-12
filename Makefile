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
# Run the Redfin CSV adapter once and write data/YYYY-MM-DD.json.
# `--month current` resolves to the previous calendar month — Redfin's
# city tracker publishes month M's data in the first half of month M+1.
# Pass explicit paths so the install-vs-repo path resolution doesn't drop
# outputs into .venv/lib/python3.12/data/ (cli.py's REPO_ROOT default uses
# `parents[2]` which is wrong when the package is installed into the venv).
ingest:
	uv run python -m adapters.cli redfin --month current \
		--data-root data \
		--sources-path data/sources.json

# Regenerate the static status page from data/sources.json. Pass explicit
# paths so the install-vs-repo path layout doesn't confuse the resolver.
status:
	uv run python -m observability.status_page \
		--sources data/sources.json \
		--output status/index.html

# ── Database (Neon) ────────────────────────────────────────────────────
# Alembic env.py auto-loads .env via python-dotenv, so no shell sourcing
# (which would mis-parse `&` in connection strings).
# `script_location` in alembic.ini is repo-root-relative, so we MUST invoke
# from the repo root and point -c at the config file.
migrate:
	uv run alembic -c infra/migrations/alembic.ini upgrade head

migrate-down:
	uv run alembic -c infra/migrations/alembic.ini downgrade -1

migrate-status:
	uv run alembic -c infra/migrations/alembic.ini current
	uv run alembic -c infra/migrations/alembic.ini history --verbose

# Verify the §9 acceptance queries from docs/seed-data.md
verify-seed:
	uv run python infra/migrations/verify_seed.py

# ── Cleanup ────────────────────────────────────────────────────────────
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
