#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/helpers/sim_structured_logging.sh
# Purpose: Shared JSONL logging helpers for simulation orchestration scripts.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/helpers/sim_structured_logging.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

# Shared JSONL logging helpers for simulation orchestration scripts.

sim_structured_log_is_enabled() {
  local enabled="${SIM_STRUCTURED_LOGS_ENABLED:-1}"
  [[ "$enabled" == "1" ]]
}

sim_structured_log_escape_json() {
  local text="$1"
  text=${text//\\/\\\\}
  text=${text//"/\\"}
  text=${text//$'\n'/\\n}
  text=${text//$'\r'/\\r}
  text=${text//$'\t'/\\t}
  printf '%s' "$text"
}

sim_structured_log_emit() {
  local path="$1"
  local logger="$2"
  local level="$3"
  local message="$4"
  local timestamp
  local escaped_logger
  local escaped_level
  local escaped_message

  if ! sim_structured_log_is_enabled; then
    return 0
  fi

  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  escaped_logger="$(sim_structured_log_escape_json "$logger")"
  escaped_level="$(sim_structured_log_escape_json "$level")"
  escaped_message="$(sim_structured_log_escape_json "$message")"

  mkdir -p "$(dirname "$path")" 2>/dev/null || return 0
  printf '{"timestamp_utc":"%s","logger":"%s","level":"%s","pid":%s,"message":"%s"}\n' \
    "$timestamp" "$escaped_logger" "$escaped_level" "$$" "$escaped_message" >> "$path" 2>/dev/null || true
}
