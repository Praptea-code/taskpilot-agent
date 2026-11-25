.PHONY: install run test lint migrate demo-calendar

install:
	python -m pip install -e ".[dev]"

run:
	python -m uvicorn agent.main:app --reload

test:
	python -m pytest

lint:
	python -m ruff check .

migrate:
	python -m alembic upgrade head

demo-calendar:
	python scripts/demo_calendar.py $(ARGS)
