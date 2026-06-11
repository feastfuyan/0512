.PHONY: setup test test-adversarial test-golden smoke lint fmt daily grafana jaeger budget rollback clean

PYTHON := python3.11
VENV := .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	@echo "✓ venv ready at $(VENV). Activate: source $(VENV)/bin/activate"

test:
	$(PYTEST) tests/unit/ tests/adversarial/ -v --tb=short

test-adversarial:
	$(PYTEST) tests/adversarial/ -v --tb=short
	@echo "✓ All 50 PI cases must show PASS — if any FAIL, do NOT merge."

test-golden:
	$(PYTEST) tests/e2e/ -v --tb=short -m golden

smoke:
	STOCKSTUDY_MOCK_LLM=true $(PY) -m workflows.daily_run --asof 2024-09-30

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/mypy schemas/ safety/ observability/

fmt:
	$(VENV)/bin/black .
	$(VENV)/bin/isort .

daily:
	@test -n "$$ANTHROPIC_API_KEY" || (echo "ANTHROPIC_API_KEY not set"; exit 1)
	$(PY) -m workflows.daily_run

grafana:
	@open http://localhost:3000 2>/dev/null || xdg-open http://localhost:3000 2>/dev/null || echo "Open http://localhost:3000"

jaeger:
	@open http://localhost:16686 2>/dev/null || xdg-open http://localhost:16686 2>/dev/null || echo "Open http://localhost:16686"

budget:
	$(PY) -m observability.cost_ledger --report month

rollback:
	@test -n "$(PROMPT)" || (echo "Usage: make rollback PROMPT=agent_xt_reasoner@v1.0.0"; exit 1)
	$(PY) -m prompts.registry --pin $(PROMPT)

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache **/__pycache__ .coverage
