.PHONY: install run test lint check migrate demo-calendar demo-sales demo-offline

install:
	python -m pip install -e ".[dev]"

run:
	python -m uvicorn agent.main:app --reload

test:
	python -m pytest

lint:
	python -m ruff check .

check:
	python -m pytest -q
	python -m ruff check .

migrate:
	python -m alembic upgrade head

demo-calendar:
	python scripts/demo_calendar.py $(ARGS)

demo-sales:
	python scripts/demo_sales.py $(ARGS)

demo-offline:
	LLM_PROVIDER=fake DATABASE_URL=sqlite+aiosqlite:///./demo_sales.db python scripts/demo_sales.py --fake
