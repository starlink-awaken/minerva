# Contributing to Minerva

Thank you for your interest in contributing to Minerva. This document outlines the process for contributing code, documentation, and bug reports.

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

1. Search [existing issues](https://github.com/minerva/minerva/issues) to avoid duplicates.
2. Use the **Bug Report** issue template.
3. Include: version (`minerva --version`), OS, Python version, steps to reproduce, expected vs actual behavior, relevant logs.

### Suggesting Features

1. Search existing issues and discussions.
2. Use the **Feature Request** issue template.
3. Describe: the problem being solved, the proposed solution, alternatives considered, how it fits Minerva's local-first philosophy.

### Pull Requests

1. **Fork** the repository and create a feature branch from `main`.
2. **Install dev dependencies:** `pip install -e ".[dev]"`.
3. **Write tests** for new functionality. Target 80%+ coverage for new code.
4. **Run linting:** `ruff check src/minerva/ --select F`.
5. **Run tests:** `pytest tests/ -q --tb=short`.
6. **Pre-commit:** Install hooks with `pre-commit install`.
7. **Commit:** Use conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
8. **Push** and open a PR against `main`.
9. Ensure CI passes (lint + tests across Python 3.11/3.12/3.13).

### Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — adding or updating tests
- `chore:` — tooling, CI, dependencies

## Development Setup

```bash
git clone https://github.com/minerva/minerva.git
cd minerva
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
minerva init
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full system architecture.

Key layers:
- **Pipeline** (`src/minerva/pipeline/`): 5-tier research execution engine
- **Search** (`src/minerva/search/`): 8 search backends with RRF fusion
- **Knowledge** (`src/minerva/knowledge/`): SQLite + Neo4j + LanceDB + RAG
- **LLM** (`src/minerva/llm/`): Multi-provider client with circuit breaker
- **Web** (`src/minerva/web/`): FastAPI app with SSE + PDF export
- **Paradigm** (`src/minerva/paradigm/`): Sophia engine integration

## Testing

```bash
# Run all tests
pytest tests/ -q

# Run with coverage
pytest tests/ --cov=src/minerva --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_stages.py -v
```

## Style Guide

- Python 3.11+ with type hints on public APIs
- `ruff` for linting and formatting (100 char line length)
- `structlog` for structured logging
- Async/await for I/O-bound operations
- Docstrings for public modules, classes, and functions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
