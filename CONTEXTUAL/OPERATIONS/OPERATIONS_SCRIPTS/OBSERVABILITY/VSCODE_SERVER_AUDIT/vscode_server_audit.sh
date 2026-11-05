#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/OBSERVABILITY/VSCODE_SERVER_AUDIT/vscode_server_audit.sh
# Purpose: Detect stale, high-consuming, suboptimal, and suspicious VS Code server processes.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-17
# Runtime: bash
# Usage: bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/OBSERVABILITY/VSCODE_SERVER_AUDIT/vscode_server_audit.sh [options]
# Inputs: Live process table from ps plus CLI thresholds.
# Outputs: Terminal report and optional kill-plan shell script.
# Notes: Read-only by default; emits suggestions without killing processes.
# =============================================================================

set -euo pipefail

STALE_SECONDS="${STALE_SECONDS:-7200}"
CPU_THRESHOLD="${CPU_THRESHOLD:-8.0}"
MEM_THRESHOLD="${MEM_THRESHOLD:-5.0}"
RSS_THRESHOLD_MIB="${RSS_THRESHOLD_MIB:-800}"
MAX_SERVER_MAIN="${MAX_SERVER_MAIN:-1}"
MAX_EXTENSION_HOST_PER_SERVER="${MAX_EXTENSION_HOST_PER_SERVER:-2}"
TOP_N="${TOP_N:-20}"
EMIT_KILL_SCRIPT=""

usage() {
  cat <<'EOF'
vscode_server_audit.sh
Classify VS Code server processes into suspicious categories.

Usage:
  vscode_server_audit.sh [options]

Options:
  --stale-seconds N                 Mark long-lived candidates as stale (default: 7200)
  --cpu-threshold PCT               Flag high CPU processes (default: 8.0)
  --mem-threshold PCT               Flag high MEM% processes (default: 5.0)
  --rss-threshold-mib MIB           Flag high RSS processes (default: 800)
  --max-server-main N               Expected max concurrent server-main roots (default: 1)
  --max-extension-host-per-server N Expected max extension hosts per server-main (default: 2)
  --top N                           Max rows in each output section (default: 20)
  --emit-kill-script PATH           Write a kill plan script (not executed)
  -h, --help                        Show this help

Classification labels:
  WRONG_*       Clearly broken/suspicious process topology.
  STALE_*       Long-lived likely stale candidates.
  SUBOPT_*      Process topology is likely inefficient.
  HIGH_USAGE    Above CPU/MEM/RSS thresholds.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stale-seconds)
      STALE_SECONDS="${2:-}"
      shift 2
      ;;
    --cpu-threshold)
      CPU_THRESHOLD="${2:-}"
      shift 2
      ;;
    --mem-threshold)
      MEM_THRESHOLD="${2:-}"
      shift 2
      ;;
    --rss-threshold-mib)
      RSS_THRESHOLD_MIB="${2:-}"
      shift 2
      ;;
    --max-server-main)
      MAX_SERVER_MAIN="${2:-}"
      shift 2
      ;;
    --max-extension-host-per-server)
      MAX_EXTENSION_HOST_PER_SERVER="${2:-}"
      shift 2
      ;;
    --top)
      TOP_N="${2:-}"
      shift 2
      ;;
    --emit-kill-script)
      EMIT_KILL_SCRIPT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! "$STALE_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "--stale-seconds must be a non-negative integer" >&2
  exit 1
fi

if [[ ! "$MAX_SERVER_MAIN" =~ ^[0-9]+$ ]]; then
  echo "--max-server-main must be a non-negative integer" >&2
  exit 1
fi

if [[ ! "$MAX_EXTENSION_HOST_PER_SERVER" =~ ^[0-9]+$ ]]; then
  echo "--max-extension-host-per-server must be a non-negative integer" >&2
  exit 1
fi

if [[ ! "$TOP_N" =~ ^[0-9]+$ ]] || [[ "$TOP_N" -lt 1 ]]; then
  echo "--top must be a positive integer" >&2
  exit 1
fi

if ! awk -v x="$CPU_THRESHOLD" 'BEGIN{exit !(x ~ /^[0-9]+(\.[0-9]+)?$/)}'; then
  echo "--cpu-threshold must be numeric" >&2
  exit 1
fi

if ! awk -v x="$MEM_THRESHOLD" 'BEGIN{exit !(x ~ /^[0-9]+(\.[0-9]+)?$/)}'; then
  echo "--mem-threshold must be numeric" >&2
  exit 1
fi

if ! awk -v x="$RSS_THRESHOLD_MIB" 'BEGIN{exit !(x ~ /^[0-9]+(\.[0-9]+)?$/)}'; then
  echo "--rss-threshold-mib must be numeric" >&2
  exit 1
fi

tmp_raw="$(mktemp /tmp/vscode_server_audit_raw.XXXXXX)"
tmp_records="$(mktemp /tmp/vscode_server_audit_records.XXXXXX)"
tmp_issues="$(mktemp /tmp/vscode_server_audit_issues.XXXXXX)"
tmp_sorted="$(mktemp /tmp/vscode_server_audit_sorted.XXXXXX)"
tmp_topology="$(mktemp /tmp/vscode_server_audit_topology.XXXXXX)"
tmp_hot_cpu="$(mktemp /tmp/vscode_server_audit_hot_cpu.XXXXXX)"
tmp_hot_rss="$(mktemp /tmp/vscode_server_audit_hot_rss.XXXXXX)"

cleanup() {
  if [[ "${KEEP_TMP:-0}" == "1" ]]; then
    echo "DEBUG_KEEP_TMP=1: preserving temp files:" >&2
    echo "  $tmp_raw" >&2
    echo "  $tmp_records" >&2
    echo "  $tmp_issues" >&2
    echo "  $tmp_sorted" >&2
    echo "  $tmp_topology" >&2
    echo "  $tmp_hot_cpu" >&2
    echo "  $tmp_hot_rss" >&2
    return 0
  fi
  rm -f "$tmp_raw" "$tmp_records" "$tmp_issues" "$tmp_sorted" "$tmp_topology" "$tmp_hot_cpu" "$tmp_hot_rss"
}
trap cleanup EXIT

ps -eo pid=,ppid=,etimes=,%cpu=,%mem=,rss=,args= > "$tmp_raw"

awk -v self_pid="$$" '
  function trim(s) {
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
    return s
  }

  function role_of(cmd) {
    if (cmd ~ /out\/server-main\.js/) return "server_main"
    if (cmd ~ /server\/bin\/code-server --connection-token=/) return "server_shell"
    if (cmd ~ /--type=extensionHost/) return "extension_host"
    if (cmd ~ /--type=fileWatcher/) return "file_watcher"
    if (cmd ~ /--type=ptyHost/) return "pty_host"
    if (cmd ~ /vscode-pylance/ || cmd ~ /server\.bundle\.js --cancellationReceive=/) return "pylance"
    if (cmd ~ /vscode-python-envs/ || cmd ~ /python-env-tools\/bin\/pet server/) return "python_env_server"
    if (cmd ~ /openai\.chat.*\/codex app-server/) return "codex_app"
    if (cmd ~ /anthropic\.claude-code/ || cmd ~ /native-binary\/claude/) return "claude_agent"
    if (cmd ~ /node_modules\/@vscode\/ripgrep\/bin\/rg /) return "ripgrep_worker"
    if (cmd ~ /command-shell --cli-data-dir/) return "command_shell"
    return "other"
  }

  {
    pid=$1
    ppid=$2
    etimes=$3
    cpu=$4+0
    mem=$5+0
    rss_kib=$6+0
    $1=$2=$3=$4=$5=$6=""
    cmd=trim($0)

    if (pid == self_pid) next
    if (cmd == "") next

    # Keep only VS Code remote server tree processes.
    if (index(cmd, "/.vscode-server/") == 0 && index(cmd, "code-server --connection-token=") == 0) next
    if (cmd ~ /vscode_server_audit\.sh/) next

    gsub(/\t/, " ", cmd)
    role=role_of(cmd)
    printf "%s\t%s\t%s\t%.3f\t%.3f\t%s\t%s\t%s\n", pid, ppid, etimes, cpu, mem, rss_kib, role, cmd
  }
' "$tmp_raw" > "$tmp_records"

if [[ ! -s "$tmp_records" ]]; then
  echo "No VS Code server processes detected."
  exit 0
fi

awk -F'\t' \
  -v stale_seconds="$STALE_SECONDS" \
  -v cpu_threshold="$CPU_THRESHOLD" \
  -v mem_threshold="$MEM_THRESHOLD" \
  -v rss_threshold_mib="$RSS_THRESHOLD_MIB" \
  -v max_server_main="$MAX_SERVER_MAIN" \
  -v max_ext_host_per_server="$MAX_EXTENSION_HOST_PER_SERVER" \
  '
  function emit_issue(score, label, pid, ppid, etimes, cpu, mem, rss_kib, role, reason, cmd) {
    printf "%03d\t%s\t%s\t%s\t%s\t%.3f\t%.3f\t%s\t%s\t%s\t%s\n", score, label, pid, ppid, etimes, cpu, mem, rss_kib, role, reason, cmd
  }

  {
    pid=$1
    ppid=$2
    etimes=$3+0
    cpu=$4+0
    mem=$5+0
    rss_kib=$6+0
    role=$7
    cmd=$8
    for (i=9; i<=NF; i++) {
      cmd = cmd "\t" $i
    }

    pid_exists[pid]=1
    ppid_of[pid]=ppid
    etimes_of[pid]=etimes
    cpu_of[pid]=cpu
    mem_of[pid]=mem
    rss_of[pid]=rss_kib
    role_by_pid[pid]=role
    cmd_of[pid]=cmd

    total_count += 1
    role_count[role] += 1

    if (role == "server_main") {
      server_count += 1
      server_pid[server_count]=pid
      if (youngest_server_pid == "" || etimes < youngest_server_age) {
        youngest_server_pid = pid
        youngest_server_age = etimes
      }
    }

    if (role == "extension_host") {
      ext_count_by_ppid[ppid] += 1
      if (!(ppid in oldest_ext_pid_by_ppid) || etimes > oldest_ext_age_by_ppid[ppid]) {
        oldest_ext_age_by_ppid[ppid] = etimes
        oldest_ext_pid_by_ppid[ppid] = pid
      }
    }
  }

  END {
    # Topology summary first.
    printf "TOTAL\t%d\n", total_count > "/dev/stderr"
    for (r in role_count) {
      printf "ROLE\t%s\t%d\n", r, role_count[r] > "/dev/stderr"
    }
    printf "SERVER_MAIN_COUNT\t%d\n", server_count > "/dev/stderr"
    printf "YOUNGEST_SERVER_MAIN_PID\t%s\n", youngest_server_pid > "/dev/stderr"

    if (server_count > max_server_main) {
      for (i = 1; i <= server_count; i++) {
        spid = server_pid[i]
        if (spid != youngest_server_pid) {
          emit_issue(
            88,
            "SUBOPT_DUP_SERVER_MAIN",
            spid,
            ppid_of[spid],
            etimes_of[spid],
            cpu_of[spid],
            mem_of[spid],
            rss_of[spid],
            role_by_pid[spid],
            "multiple server-main roots; older root is likely stale or unnecessary",
            cmd_of[spid]
          )
        }
      }
    }

    for (pp in ext_count_by_ppid) {
      if (ext_count_by_ppid[pp] > max_ext_host_per_server) {
        opid = oldest_ext_pid_by_ppid[pp]
        emit_issue(
          72,
          "SUBOPT_EXCESS_EXTENSION_HOSTS",
          opid,
          ppid_of[opid],
          etimes_of[opid],
          cpu_of[opid],
          mem_of[opid],
          rss_of[opid],
          role_by_pid[opid],
          "more extension hosts than expected under same server-main",
          cmd_of[opid]
        )
      }
    }

    for (pid in pid_exists) {
      ppid = ppid_of[pid]
      etimes = etimes_of[pid]
      cpu = cpu_of[pid]
      mem = mem_of[pid]
      rss_kib = rss_of[pid]
      rss_mib = rss_kib / 1024.0
      role = role_by_pid[pid]
      cmd = cmd_of[pid]

      # Clearly suspicious: worker-like process with no valid parent.
      if (role ~ /^(extension_host|file_watcher|pty_host|pylance|python_env_server|codex_app|claude_agent|ripgrep_worker|command_shell)$/) {
        if (!(ppid in pid_exists) && ppid != 1) {
          emit_issue(95, "WRONG_MISSING_PARENT", pid, ppid, etimes, cpu, mem, rss_kib, role,
            "worker process parent is missing", cmd)
        }
        if (ppid == 1) {
          emit_issue(93, "WRONG_ORPHANED_WORKER", pid, ppid, etimes, cpu, mem, rss_kib, role,
            "worker process is orphaned under init", cmd)
        }
      }

      # Stale candidates.
      if (etimes >= stale_seconds) {
        if (role == "server_main" && pid != youngest_server_pid) {
          emit_issue(84, "STALE_OLD_SERVER_MAIN", pid, ppid, etimes, cpu, mem, rss_kib, role,
            "older root server-main process exceeds stale threshold", cmd)
        } else if (role != "server_shell") {
          emit_issue(63, "STALE_LONG_LIVED", pid, ppid, etimes, cpu, mem, rss_kib, role,
            "process exceeds stale threshold", cmd)
        }
      }

      # Resource-heavy candidates.
      if (cpu >= cpu_threshold || mem >= mem_threshold || rss_mib >= rss_threshold_mib) {
        emit_issue(52, "HIGH_USAGE", pid, ppid, etimes, cpu, mem, rss_kib, role,
          "resource usage above configured threshold", cmd)
      }
    }
  }
' "$tmp_records" > "$tmp_issues" 2> "$tmp_topology"

sort -t$'\t' -k1,1nr -k5,5nr -k6,6nr "$tmp_issues" > "$tmp_sorted"
sort -t$'\t' -k4,4nr "$tmp_records" > "$tmp_hot_cpu"
sort -t$'\t' -k6,6nr "$tmp_records" > "$tmp_hot_rss"

echo "VS Code Server Audit Snapshot"
echo "timestamp_utc: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "thresholds: stale_seconds=$STALE_SECONDS cpu_pct=$CPU_THRESHOLD mem_pct=$MEM_THRESHOLD rss_mib=$RSS_THRESHOLD_MIB max_server_main=$MAX_SERVER_MAIN max_ext_host_per_server=$MAX_EXTENSION_HOST_PER_SERVER"
echo

echo "Topology summary:"
awk -F'\t' '
  $1=="TOTAL" {printf "  total_vscode_processes: %s\n", $2}
  $1=="SERVER_MAIN_COUNT" {printf "  server_main_count: %s\n", $2}
  $1=="YOUNGEST_SERVER_MAIN_PID" {printf "  youngest_server_main_pid: %s\n", $2}
  $1=="ROLE" {printf "  role_%s: %s\n", $2, $3}
' "$tmp_topology" | sort
echo

echo "Flagged candidates (highest severity first):"
if [[ -s "$tmp_sorted" ]]; then
  {
    echo -e "score\tlabel\tpid\tppid\tage_s\tcpu%\tmem%\trss_mib\trole\treason"
    awk -F'\t' -v top_n="$TOP_N" 'NR<=top_n {
      printf "%s\t%s\t%s\t%s\t%s\t%.2f\t%.2f\t%.1f\t%s\t%s\n", $1, $2, $3, $4, $5, $6, $7, ($8/1024.0), $9, $10
    }' "$tmp_sorted"
  } | column -t -s $'\t'
else
  echo "  no candidates flagged"
fi
echo

echo "Top consumers by CPU (%):"
{
  echo -e "pid\tppid\tage_s\tcpu%\tmem%\trss_mib\trole\tcmd"
  awk -F'\t' -v top_n="$TOP_N" 'NR<=top_n {
    printf "%s\t%s\t%s\t%.2f\t%.2f\t%.1f\t%s\t%s\n", $1, $2, $3, $4, $5, ($6/1024.0), $7, $8
  }' "$tmp_hot_cpu"
} | column -t -s $'\t'
echo

echo "Top consumers by RSS (MiB):"
{
  echo -e "pid\tppid\tage_s\trss_mib\tcpu%\tmem%\trole\tcmd"
  awk -F'\t' -v top_n="$TOP_N" 'NR<=top_n {
    printf "%s\t%s\t%s\t%.1f\t%.2f\t%.2f\t%s\t%s\n", $1, $2, $3, ($6/1024.0), $4, $5, $7, $8
  }' "$tmp_hot_rss"
} | column -t -s $'\t'
echo

if [[ -n "$EMIT_KILL_SCRIPT" ]]; then
  mkdir -p "$(dirname "$EMIT_KILL_SCRIPT")"
  {
    echo "#!/usr/bin/env bash"
    echo "set -euo pipefail"
    echo "# Generated by vscode_server_audit.sh at $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "# Review before executing."
    awk -F'\t' '
      ($2 ~ /^WRONG_/) || ($2 ~ /^STALE_/) || ($2 ~ /^SUBOPT_/) {
        if (!seen[$3]++) {
          printf "kill %s  # %s | %s | %s\n", $3, $2, $9, $10
        }
      }
    ' "$tmp_sorted"
  } > "$EMIT_KILL_SCRIPT"
  chmod +x "$EMIT_KILL_SCRIPT"
  echo "Kill-plan script written to: $EMIT_KILL_SCRIPT"
fi

echo "Safety: this audit does not kill any process unless you run a generated kill-plan script manually."
