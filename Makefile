ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CASE ?=

.PHONY: check test-integration test-e2e test-mutation dev-api dev-web
check:
	uv run --directory "$(ROOT)/backend" --no-sync ruff check .
	uv run --directory "$(ROOT)/backend" --no-sync ruff format --check .
	uv run --directory "$(ROOT)/backend" --no-sync ruff check --config "$(ROOT)/backend/pyproject.toml" "$(ROOT)/scripts"
	uv run --directory "$(ROOT)/backend" --no-sync ruff format --check --config "$(ROOT)/backend/pyproject.toml" "$(ROOT)/scripts"
	pnpm --dir "$(ROOT)/frontend" typecheck
	pnpm --dir "$(ROOT)/frontend" build

test-integration:
	python3 "$(ROOT)/scripts/with-test-postgres.py" uv run --directory "$(ROOT)/backend" --no-sync pytest $(if $(CASE),-k "$(CASE)",)

test-e2e:
	python3 "$(ROOT)/scripts/with-test-postgres.py" python3 "$(ROOT)/scripts/migrate-and-run.py" pnpm --dir "$(ROOT)/frontend" test:e2e $(if $(CASE),--grep "$(CASE)",)

test-mutation:
	python3 "$(ROOT)/scripts/check-title-mutation.py"
	python3 "$(ROOT)/scripts/check-download-mutations.py"
	python3 "$(ROOT)/scripts/check-subtitle-mutation.py"
	python3 "$(ROOT)/scripts/with-test-postgres.py" python3 "$(ROOT)/scripts/check-auth-mutations.py"

dev-api:
	python3 "$(ROOT)/scripts/dev-api.py"

dev-web:
	pnpm --dir "$(ROOT)/frontend" dev
