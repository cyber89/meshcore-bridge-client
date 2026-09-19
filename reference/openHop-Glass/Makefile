.PHONY: init-env init-prod-env easy-start dev-up dev-down dev-logs prod-up prod-down prod-logs changelog changelog-preview changelog-unreleased patch patch-dry-run backend-venv backend-install-dev backend-dev backend-lint backend-test backend-test-cov backend-check frontend-install frontend-dev frontend-build

COMPOSE_DEV = docker compose
COMPOSE_PROD = docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml
CLIFF = git-cliff
CLIFF_CONFIG = cliff.toml
CHANGELOG_FILE = CHANGELOG.md

init-env:
	cp -n .env.example .env || true
	cp -n backend/.env.example backend/.env || true
	cp -n frontend/.env.example frontend/.env || true
init-prod-env:
	cp -n .env.production.example .env.production || true
	cp -n backend/.env.production.example backend/.env.production || true
easy-start:
	./scripts/easy-start.sh

dev-up:
	$(COMPOSE_DEV) up -d --build

dev-down:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f backend frontend postgres mosquitto

prod-up:
	$(COMPOSE_PROD) up -d --build

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f backend frontend postgres mosquitto

changelog:
	$(CLIFF) --config $(CLIFF_CONFIG) --output $(CHANGELOG_FILE)

changelog-preview:
	$(CLIFF) --config $(CLIFF_CONFIG) --unreleased

changelog-unreleased:
	$(CLIFF) --config $(CLIFF_CONFIG) --unreleased --output $(CHANGELOG_FILE)

patch:
	./scripts/release-patch.sh "$(NOTE)"

patch-dry-run:
	./scripts/release-patch.sh --dry-run "$(NOTE)"
backend-venv:
	python3 -m venv backend/.venv

backend-install-dev: backend-venv
	backend/.venv/bin/pip install --upgrade pip
	backend/.venv/bin/pip install -e "backend[dev]"

backend-dev: backend-install-dev
	backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload --app-dir backend

backend-lint: backend-install-dev
	backend/.venv/bin/python -m ruff check backend/app backend/tests

backend-test: backend-install-dev
	backend/.venv/bin/python -m pytest backend/tests

backend-test-cov: backend-install-dev
	backend/.venv/bin/python -m pytest --cov=backend/app --cov-report=term-missing backend/tests

backend-check: backend-lint backend-test

frontend-install:
	npm --prefix frontend install

frontend-dev: frontend-install
	npm --prefix frontend run dev

frontend-build: frontend-install
	npm --prefix frontend run build

