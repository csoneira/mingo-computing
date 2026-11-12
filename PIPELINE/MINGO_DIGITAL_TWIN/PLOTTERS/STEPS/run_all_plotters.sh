#!/usr/bin/env bash
# Purpose: Run all step plotters (STEP_1 .. STEP_10) and report per-step status.

# Run all step plotters (STEP_1 .. STEP_10) and report per-step status
cd "$(dirname "$0")" || exit 2
# discover plot scripts under STEP_*/* and run each with numeric step ordering
mapfile -t SCRIPTS < <(printf '%s\n' STEP_*/plot_step_*.py 2>/dev/null | sort -V)
if [ ${#SCRIPTS[@]} -eq 0 ]; then
  echo "No step plotter scripts found under $(pwd)/STEP_*" >&2
  exit 2
fi
LOGFILE="run_all_plotters.log"
: > "$LOGFILE"
EXIT_CODE=0
for s in "${SCRIPTS[@]}"; do
  echo "=== Running $s ===" | tee -a "$LOGFILE"
  # run and capture the real python exit code (use PIPESTATUS because of tee)
  python3 "$s" 2>&1 | tee -a "$LOGFILE"
  RC=${PIPESTATUS[0]:-1}
  if [ "$RC" -eq 0 ]; then
    echo "=== $s: OK ===" | tee -a "$LOGFILE"
  else
    echo "=== $s: FAILED (exit ${RC}) ===" | tee -a "$LOGFILE"
    EXIT_CODE=1
  fi
  echo "" | tee -a "$LOGFILE"
done
echo "run_all_plotters finished with exit code ${EXIT_CODE}" | tee -a "$LOGFILE"
exit $EXIT_CODE
