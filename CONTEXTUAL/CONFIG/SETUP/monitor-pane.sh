#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../CONTENTS/environment/dataflow.sh"
mode="${1:?pane mode required}"
while true; do
    printf '\033[H\033[2JDATAFLOW %s — %s\n' "$mode" "$(date --iso-8601=seconds)"
    case "$mode" in
        flow)
            if compgen -G "$DATAFLOW_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/FILE_FLOW_TRACKER/MINGO*_file_flow_realtime.csv" >/dev/null; then
                bash "$DATAFLOW_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FILE_FLOW_TRACKER/watch_file_flow.sh" || true
            else
                echo 'Waiting for file-flow telemetry; no scientific data has been created by setup.'
            fi ;;
        processes)
            ps -u "$(id -un)" -o pid,etime,pcpu,pmem,args | awk '/DATAFLOW/ && !/monitor-pane|awk/' || true ;;
        logs)
            "$PYTHON_BIN" - "$DATAFLOW_ROOT" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1]) / 'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS'
files = sorted(root.rglob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
if not files:
    print('Waiting for execution logs.')
for path in files:
    print('\n' + str(path.relative_to(root)))
    # Bounded reads; never concatenate entire production logs.
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 4096))
        print('\n'.join(stream.read().decode(errors='replace').splitlines()[-4:]))
PY
            ;;
        *) exit 2 ;;
    esac
    [[ "${2:-}" == --once ]] && exit 0
    sleep 3
done
