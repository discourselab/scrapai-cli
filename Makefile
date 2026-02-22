# ScrapAI CLI - Development Makefile

.PHONY: help install test test-unit test-integration test-coverage clean lint format security

help:
	@echo "ScrapAI CLI - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install all dependencies (prod + dev)"
	@echo "  make install-dev      Install only dev dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-unit        Run only unit tests (fast)"
	@echo "  make test-integration Run only integration tests"
	@echo "  make test-coverage    Run tests with coverage report"
	@echo "  make test-watch       Run tests in watch mode"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run flake8 linter"
	@echo "  make format           Format code with black"
	@echo "  make format-check     Check if code is formatted"
	@echo "  make typecheck        Run mypy type checker"
	@echo ""
	@echo "Security:"
	@echo "  make security         Run security scans (safety + bandit)"
	@echo "  make security-deps    Check for vulnerable dependencies"
	@echo "  make security-code    Scan code for security issues"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove test artifacts and cache"

# Setup
install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	playwright install chromium

install-dev:
	pip install -r requirements-dev.txt

# Testing
test:
	pytest -v

test-unit:
	pytest tests/unit -v -m unit

test-integration:
	pytest tests/integration -v -m integration

test-coverage:
	pytest --cov=core --cov=spiders --cov=cli --cov=handlers --cov=utils \
		--cov-report=html --cov-report=term-missing

test-watch:
	pytest-watch -- -v

# Run specific test file
test-file:
	pytest $(FILE) -v

# Code Quality
lint:
	flake8 core spiders cli handlers utils tests

format:
	black core spiders cli handlers utils tests

format-check:
	black --check core spiders cli handlers utils tests

typecheck:
	mypy core --ignore-missing-imports

# Security
security: security-deps security-code

security-deps:
	safety check

security-code:
	bandit -r core spiders cli handlers utils

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	find . -type f -name "coverage.xml" -delete

# Quick pre-commit check
pre-commit: format-check lint test-unit
	@echo "✓ Pre-commit checks passed!"
