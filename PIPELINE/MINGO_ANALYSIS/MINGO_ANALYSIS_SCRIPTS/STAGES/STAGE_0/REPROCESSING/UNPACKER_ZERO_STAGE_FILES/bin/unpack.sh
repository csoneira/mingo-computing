# Purpose: Run the configured legacy Stage-0 HLD unpacking workflow.

# =============================================================================

# Walk up from this file to find the checkout unless DATAFLOW_ROOT is set.
if [[ -z "${DATAFLOW_ROOT:-}" ]]; then
  _repo_probe="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  while [[ "$_repo_probe" != "/" && ! -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; do
    _repo_probe="$(dirname -- "$_repo_probe")"
  done
  if [[ -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh"
  else
    echo "Could not locate repository root from ${BASH_SOURCE[0]}" >&2
    exit 2
  fi
fi
unset _repo_probe

# What to really change when the directory is changed:
#    unpack.sh, of course, the cd should lead to software
#    initConf.m, the HOME line, THAT MUST END WITH A SLASH
#    

cd ${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/software/ # <--------------------------------------------
octave --no-gui ./unpackingContinuous.m
