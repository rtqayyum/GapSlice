#!/bin/bash -l
# One-time dependency preparation on the login node; no scientific experiments.
set -euo pipefail
PROJECT="${GS_OJCS_PROJECT:-/home/tariq.qayyum/hpc/GapSlice-OJCS}"
cd "$PROJECT"
export GS_OJCS_PROJECT="$PROJECT"
source "$PROJECT/hpc/environment.sh"
source "$PROJECT/hpc/project_lock.sh"
gs_acquire_project_lock "$PROJECT"
prepare_exit() {
  local code=$?
  trap - EXIT
  if gs_release_project_lock; then :; else if [ "$code" -eq 0 ]; then code=74; fi; fi
  exit "$code"
}
trap prepare_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
type module >/dev/null 2>&1 || { printf 'ERROR: run this setup in a login shell so module is available.\n' >&2; exit 2; }
module load anaconda3
source "$PROJECT/hpc/environment.sh"
mkdir -p "$PROJECT/logs" "$PROJECT/outputs/setup"
LOG="$PROJECT/logs/prepare-$(date -u '+%Y%m%dT%H%M%SZ')-$$.log"
printf 'Preparing only this project. Setup log: %s\n' "$LOG"
bash "$PROJECT/hpc/bootstrap.sh" 2>&1 | tee "$LOG"
printf 'Checking runtime and project guard before submission.\n' | tee -a "$LOG"
"$PROJECT/.venv/bin/python" -m pytest \
  "$PROJECT/tests/test_hpc_python_runtime.py" "$PROJECT/tests/test_hpc_project_lock.py" \
  -q -p no:cacheprovider 2>&1 | tee -a "$LOG"
printf 'Preparation completed. Runtime details: %s\n' "$PROJECT/outputs/setup/runtime.json"
