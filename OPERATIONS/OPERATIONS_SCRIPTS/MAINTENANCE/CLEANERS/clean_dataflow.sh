#!/usr/bin/env bash
# Category-based cleaner; configuration and deletion logic live beside this launcher.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../../.." && pwd -P)"
CLEAN_PYTHON="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python3}"
[[ -x "$CLEAN_PYTHON" ]] || CLEAN_PYTHON=python3
exec "$CLEAN_PYTHON" "$SCRIPT_DIR/clean_dataflow.py" --root "${DATAFLOW_CLEAN_ROOT:-$REPO_ROOT}" "$@"
