.PHONY: install dev worker beat sandbox test eval lint format

install:
	uv sync

dev:
	uv run uvicorn reposage.api.main:app --port 8000

worker:
	uv run celery -A reposage.workers.celery_app worker -P threads -c 4 -l info

beat:
	uv run celery -A reposage.workers.celery_app beat -l info

sandbox:
	uv run uvicorn reposage.sandbox.runner_service:app --host 0.0.0.0 --port 9000

test:
	uv run pytest -v tests/

eval:
	uv run python -m reposage.evals.cli run --suite retrieval_v1

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/
