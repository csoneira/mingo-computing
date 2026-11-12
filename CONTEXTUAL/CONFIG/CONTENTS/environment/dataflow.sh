# Purpose: Set environment variables shared by repository dataflow scripts.

# Derive DATAFLOW_ROOT from this file, independent of the caller's directory.
export DATAFLOW_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd -P)"
export MASTER_STAGE_ROOT="$DATAFLOW_ROOT/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES"
export PYTHON_BIN="$DATAFLOW_ROOT/.venv/bin/python3"
export VIRTUAL_ENV="$DATAFLOW_ROOT/.venv"
case ":${PATH:-}:" in
    *":$VIRTUAL_ENV/bin:"*) ;;
    *) export PATH="$VIRTUAL_ENV/bin:${PATH:-/usr/bin:/bin}:/usr/sbin:/sbin" ;;
esac
