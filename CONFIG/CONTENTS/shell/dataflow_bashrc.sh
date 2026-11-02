source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../environment" && pwd)/dataflow.sh"
# Use Codex's standard user directory unless explicitly overridden.
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
watch_file_flow() {
    /bin/bash "$DATAFLOW_ROOT/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FILE_FLOW_TRACKER/watch_file_flow.sh" --interactive "$@"
}
