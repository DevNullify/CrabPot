.PHONY: build test lint install-local clean release

build:
	python -m build

test:
	python -m pytest tests/ -v --tb=short

lint:
	python -m ruff check src/ tests/
	python -m mypy src/crabpot/

install-local:
	pip install -e ".[dev]"

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

release: clean build
	@echo "Upload dist/* to GitHub releases"
