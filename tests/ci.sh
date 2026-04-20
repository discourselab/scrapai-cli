#!/usr/bin/env bash
# Reproduce the GitHub Actions CI checks locally, one at a time.
#
# Usage:
#   tests/ci.sh                # run all checks (stops on first failure)
#   tests/ci.sh black          # run only one check
#   tests/ci.sh flake8 unit    # run a subset
#
# Available checks: black, flake8, unit, integration, security, all (default)

set -uo pipefail

cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
    PY=".venv/bin/python"
elif [ -d "venv" ]; then
    PY="venv/bin/python"
else
    PY="python3"
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

step() { echo -e "\n${YELLOW}━━━ $1 ━━━${NC}"; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; FAILED+=("$1"); }

FAILED=()

ensure_dev_deps() {
    if ! "$PY" -c "import pytest, black, flake8, bandit" >/dev/null 2>&1; then
        step "installing dev deps from requirements-dev.txt"
        "$PY" -m pip install -q -r requirements-dev.txt || {
            echo -e "${RED}Failed to install requirements-dev.txt${NC}"
            exit 1
        }
    fi
}

ensure_dev_deps

run_black() {
    step "black --check"
    if "$PY" -m black --check core spiders cli handlers utils tests; then
        ok "black"
    else
        fail "black (run: $PY -m black core spiders cli handlers utils tests)"
    fi
}

run_flake8() {
    step "flake8"
    if "$PY" -m flake8 core spiders cli handlers utils tests \
            --count --statistics --max-line-length=120; then
        ok "flake8"
    else
        fail "flake8"
    fi
}

run_unit() {
    step "pytest tests/unit"
    if "$PY" -m pytest tests/unit -v -m unit --cov=core --cov=spiders; then
        ok "unit tests"
    else
        fail "unit tests"
    fi
}

run_integration() {
    step "pytest tests/integration"
    if "$PY" -m pytest tests/integration -v -m integration; then
        ok "integration tests"
    else
        fail "integration tests"
    fi
}

run_security() {
    step "bandit (security scan, advisory only)"
    "$PY" -m bandit -r core spiders cli handlers utils -ll || true
    ok "bandit (advisory)"
}

CHECKS=("${@:-all}")
if [ "${CHECKS[0]}" = "all" ]; then
    CHECKS=(black flake8 unit integration security)
fi

for check in "${CHECKS[@]}"; do
    case "$check" in
        black)       run_black ;;
        flake8)      run_flake8 ;;
        unit)        run_unit ;;
        integration) run_integration ;;
        security)    run_security ;;
        *) echo "Unknown check: $check"; exit 2 ;;
    esac
done

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo -e "${GREEN}All checks passed.${NC}"
    exit 0
else
    echo -e "${RED}Failed: ${FAILED[*]}${NC}"
    exit 1
fi
