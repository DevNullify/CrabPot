# Contributing to CrabPot

Thank you for your interest in contributing to CrabPot! This document provides guidelines and information for contributors.

## Code of Conduct

Be respectful, constructive, and collaborative. We're all here to make OpenClaw safer to run.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/crabpot.git
   cd crabpot
   ```
3. **Install in development mode**:
   ```bash
   pip install -e ".[dev]"
   ```
4. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Before you code

- Check existing [issues](https://github.com/DevNullify/crabpot/issues) to avoid duplicate work
- For significant changes, open an issue first to discuss the approach
- Read the [Development Guide](docs/development.md) for project structure details

### While coding

- Follow existing code style (enforced by `ruff`)
- Add tests for new functionality
- Keep commits focused and descriptive
- Don't break existing tests

### Before submitting

Run the full check suite:

```bash
# Tests
python -m pytest tests/ -v

# Linting
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/

# Type checking
python -m mypy src/crabpot/ --ignore-missing-imports
```

All checks must pass before submitting a PR.

## Pull Request Process

1. **Update documentation** if your change affects user-facing behavior
2. **Add tests** for new features or bug fixes
3. **Keep PRs focused** — one feature or fix per PR
4. **Write a clear PR description** explaining what and why
5. **Reference any related issues** (e.g., "Fixes #42")

### PR Title Convention

Use a descriptive title that summarizes the change:

- `Add configurable monitor thresholds`
- `Fix CPU stats calculation for multi-core`
- `Update seccomp profile for Node.js 22`

## Code Style

- **Python 3.9+** compatible code
- **Ruff** for linting and formatting (config in `pyproject.toml`)
- **Type hints** where they add clarity (not required for every function)
- **Docstrings** for classes and public methods
- Keep functions focused — if it's doing too much, split it

## Testing Guidelines

- Tests live in `tests/` and mirror the `src/crabpot/` structure
- Use `pytest` fixtures for shared setup
- Mock Docker SDK calls — tests should not require a running Docker daemon
- Test both success and failure paths
- For threading tests, use short timeouts to keep tests fast

### Running specific tests

```bash
# All tests
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_alerts.py -v

# Single test
python -m pytest tests/test_alerts.py::TestAlertDispatcher::test_fire_writes_log -v

# With coverage
python -m pytest tests/ --cov=crabpot --cov-report=html
```

## Areas for Contribution

### Good first issues

- Add more alert patterns to `LOG_PATTERNS` in `monitor.py`
- Improve error messages in CLI commands
- Add more tests for edge cases

### Medium complexity

- Configurable monitor thresholds via config file
- Network connection whitelisting
- Dashboard dark/light theme toggle

### Advanced

- Rootless Docker support
- Multiple container profiles
- Plugin system for custom monitors
- Integration with external alerting (PagerDuty, Slack)

## Security

If you find a security vulnerability, **do not open a public issue**. Instead, report it privately via GitHub's security advisory feature or email the maintainers directly.

## Questions?

Open a [discussion](https://github.com/DevNullify/crabpot/discussions) or create an issue tagged with `question`.
