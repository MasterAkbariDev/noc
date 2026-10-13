UV := $(shell command -v uv 2>/dev/null || echo .tools/bin/uv)
COMPOSE := docker compose -f deploy/noc/docker-compose.yml
TEST_DB_NAME ?= noc_test
TEST_DB := postgresql+psycopg://noc:noc@localhost:5432/$(TEST_DB_NAME)

.PHONY: setup lint format typecheck test test-integration check db-up db-down migrate rules-test dev-key sentinel-dev api worker

setup:
	$(UV) sync

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/python scripts/check_doc_links.py

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

typecheck:
	.venv/bin/mypy shared/src sentinel/src noc/src

test:
	.venv/bin/pytest tests/unit -q

test-integration: db-up
	$(COMPOSE) exec -T postgres psql -U noc -d noc -tc "SELECT 1 FROM pg_database WHERE datname='$(TEST_DB_NAME)'" | grep -q 1 || \
		$(COMPOSE) exec -T postgres psql -U noc -d noc -c "CREATE DATABASE $(TEST_DB_NAME)"
	NOC_TEST_DATABASE_URL=$(TEST_DB) .venv/bin/pytest tests -q

check: lint typecheck test-integration

db-up:
	$(COMPOSE) up -d --wait postgres

db-down:
	$(COMPOSE) down

migrate: db-up
	.venv/bin/noc db upgrade

rules-test:
	docker run --rm -v "$(CURDIR)/deploy/noc/prometheus:/prom" -w /prom/rule-tests --entrypoint sh prom/prometheus:v3.10.0 -c 'promtool check rules /prom/rules/*.yml && promtool test rules *.yml'

dev-key:
	mkdir -p deploy/noc/keys
	test -f deploy/noc/keys/noc-dev.key || openssl rand -hex 32 > deploy/noc/keys/noc-dev.key

sentinel-dev: dev-key
	.venv/bin/noc-sentinel --config deploy/target/sentinel/dev-loopback.yaml --insecure-loopback

api:
	.venv/bin/noc api

worker:
	.venv/bin/noc worker
