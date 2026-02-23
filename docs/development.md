# Development Guide

This guide covers setting up a development environment, project structure, running tests, and building releases.

## Setup

### Clone the repository

```bash
git clone https://github.com/DevNullify/crabpot.git
cd crabpot
```

### Install in development mode

```bash
pip install -e ".[dev]"
```

This installs `crabpot` in editable mode along with development dependencies (pytest, ruff, mypy).

### Verify installation

```bash
crabpot --version
python -m pytest tests/ -v
```

## Project Structure

```
CrabPot/
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI: test, lint, typecheck, security audit
│       ├── release.yml         # Build + GitHub Release + PyPI publish
│       └── codeql.yml          # GitHub CodeQL security analysis
├── docs/
│   ├── getting-started.md      # Installation and first run
│   ├── security.md             # Security model deep dive
│   ├── monitoring.md           # Monitoring and alerts guide
│   ├── dashboard.md            # Web dashboard guide
│   └── development.md          # This file
├── src/
│   └── crabpot/
│       ├── __init__.py         # Version info
│       ├── __main__.py         # CLI entry point (argparse)
│       ├── cli.py              # Command handlers
│       ├── docker_manager.py   # Docker SDK wrapper
│       ├── config_generator.py # Docker config generation
│       ├── monitor.py          # 6-channel security monitor
│       ├── alerts.py           # Multi-channel alert dispatcher
│       ├── dashboard.py        # Flask + SocketIO server
│       ├── dashboard_html.py   # Embedded HTML/CSS/JS
│       ├── tui.py              # Rich terminal dashboard
│       └── templates/
│           ├── docker-compose.yml.j2
│           ├── Dockerfile.j2
│           └── seccomp-profile.json
├── tests/
│   ├── test_alerts.py          # 16 tests
│   ├── test_config_generator.py # 7 tests
│   ├── test_docker_manager.py  # 14 tests
│   └── test_monitor.py         # 8 tests
├── install.sh                  # curl-pipe-sh installer
├── pyproject.toml              # Package configuration
├── Makefile                    # Build automation
└── CONTRIBUTING.md             # Contribution guidelines
```

## Module Overview

| Module | Responsibility |
|--------|----------------|
| `__main__.py` | Parses CLI arguments with argparse, dispatches to `cli.py` |
| `cli.py` | Implements each CLI command, orchestrates other modules |
| `docker_manager.py` | Wraps the Docker SDK for container lifecycle, stats, exec |
| `config_generator.py` | Renders Jinja2 templates into hardened Docker configs |
| `monitor.py` | Runs 6 concurrent monitoring threads |
| `alerts.py` | Routes alerts to terminal, log file, WebSocket, Windows toast |
| `dashboard.py` | Flask app with SocketIO for real-time web dashboard |
| `dashboard_html.py` | Single HTML string with embedded CSS and JavaScript |
| `tui.py` | Rich-based terminal UI with keyboard controls |

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_alerts.py -v

# Run with coverage
python -m pytest tests/ --cov=crabpot --cov-report=term-missing

# Run a specific test
python -m pytest tests/test_docker_manager.py::TestDockerManager::test_pause_running_container -v
```

Tests use `pytest` with `unittest.mock` for Docker SDK mocking. No real Docker daemon is needed to run tests.

## Linting

```bash
# Check for issues
python -m ruff check src/ tests/

# Auto-fix issues
python -m ruff check --fix src/ tests/

# Format code
python -m ruff format src/ tests/

# Check formatting without changes
python -m ruff format --check src/ tests/
```

## Type Checking

```bash
python -m mypy src/crabpot/ --ignore-missing-imports
```

## Building

```bash
# Build sdist and wheel
python -m build

# Output in dist/
ls dist/
# crabpot-1.0.0.tar.gz
# crabpot-1.0.0-py3-none-any.whl
```

## Releasing

Releases are automated via GitHub Actions. To create a release:

1. Update the version in `src/crabpot/__init__.py` and `pyproject.toml`
2. Commit the version bump
3. Create and push a tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
4. The `release.yml` workflow will:
   - Run the test suite
   - Build the distribution
   - Create a GitHub Release with the artifacts
   - Publish to PyPI (if configured)

## Makefile Targets

```bash
make build          # Build Python package
make test           # Run pytest
make lint           # Run ruff and mypy
make install-local  # pip install -e ".[dev]"
make clean          # Remove build artifacts
make release        # Clean + build
```

## Architecture Decisions

### Why threading over asyncio?

The Docker SDK (`docker-py`) is synchronous. Each of the 6 monitor watchers runs its own blocking loop (stats streaming, event listening, periodic polling). Daemon threads provide natural cleanup when the main process exits, and `threading.Event` gives cooperative cancellation.

### Why embedded HTML?

The dashboard HTML is embedded as a Python string in `dashboard_html.py` rather than served as static files. This eliminates file-path discovery issues across different installation methods and keeps the package self-contained.

### Why not use Docker Compose SDK?

The `docker compose` CLI is more reliable for build operations than the Python SDK's compose support. We use the Docker SDK for container-level operations (stats, exec, events) but shell out to `docker compose` for build and up/down.

### Why `src/` layout?

The `src/` layout prevents accidental imports of the local package during development. It's the recommended layout for modern Python packages.
