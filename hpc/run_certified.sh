#!/bin/bash -l
# One command: check both allocations, run a small pipeline, then a frozen study.
set -euo pipefail
PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
MODE="${1:-research}"
CPUS="${GS_CERT_CPUS:-160}"
case "$MODE" in smoke|research|resume) ;; *) echo 'Usage: bash hpc/run_certified.sh smoke|research|resume' >&2; exit 2 ;; esac
case "$CPUS" in ''|*[!0-9]*) echo 'GS_CERT_CPUS must be an integer' >&2; exit 2 ;; esac
if [ "$CPUS" -lt 1 ]; then exit 2; fi
cd "$PROJECT"
mkdir -p "$PROJECT/logs" "$PROJECT/outputs/cert/submissions" "$PROJECT/results" "$PROJECT/figures" "$PROJECT/tmp"
for SCRIPT in "$PROJECT/Batch" "$PROJECT"/hpc/*.sh; do bash -n "$SCRIPT"; done
if [ ! -x "$PROJECT/.venv/bin/python" ]; then echo 'Run bash -l hpc/prepare.sh first' >&2; exit 2; fi
limit() {
  local info value
  info="$(scontrol show partition "$1" -o)"
  value="$(printf '%s\n' "$info" | sed -n 's/.* MaxTime=\([^ ]*\).*/\1/p')"
  if [ -z "$value" ]; then echo 'Cannot read partition MaxTime' >&2; return 2; fi
  case "$value" in UNLIMITED|INFINITE) value=20-00:00:00 ;; esac
  printf '%s' "$value"
}
SHORT_TIME="$(limit shortq)"
LONG_TIME="$(limit longq)"
SMOKE=(--job-name=gs_cert_smoke --partition=shortq --ntasks=4 --cpus-per-task=1 --mem-per-cpu=2G
  --time="$SHORT_TIME" --chdir="$PROJECT" --export=ALL,GS_OJCS_STAGE=certified,GS_OJCS_PRESET=smoke)
RESEARCH=(--job-name=gs_cert_research --partition=longq --ntasks="$CPUS" --cpus-per-task=1 --mem-per-cpu=4G
  --time="$LONG_TIME" --chdir="$PROJECT" --export=ALL,GS_OJCS_STAGE=certified,GS_OJCS_PRESET=research)
# Slurm validates actual account, QOS, CPU and memory limits. Test both before
# submitting either. Never cancel unrelated jobs or edit shared installations.
if [ "$MODE" != resume ]; then sbatch --test-only "${SMOKE[@]}" "$PROJECT/Batch"; fi
if [ "$MODE" != smoke ]; then sbatch --test-only "${RESEARCH[@]}" "$PROJECT/Batch"; fi
SMOKE_ID=none
if [ "$MODE" != resume ]; then
  SMOKE_ID="$(sbatch --parsable "${SMOKE[@]}" "$PROJECT/Batch")"; SMOKE_ID="${SMOKE_ID%%;*}"
  case "$SMOKE_ID" in ''|*[!0-9]*) echo 'Unexpected Slurm smoke response' >&2; exit 2 ;; esac
  printf 'Smoke job: %s (4 CPUs, 2G/CPU, %s, no GPU)\n' "$SMOKE_ID" "$SHORT_TIME"
fi
RESEARCH_ID=none
if [ "$MODE" != smoke ]; then
  DEPENDENCY=()
  if [ "$MODE" = research ]; then DEPENDENCY=(--dependency="afterok:$SMOKE_ID"); fi
  RESEARCH_ID="$(sbatch --parsable "${RESEARCH[@]}" "${DEPENDENCY[@]}" "$PROJECT/Batch")"; RESEARCH_ID="${RESEARCH_ID%%;*}"
  case "$RESEARCH_ID" in ''|*[!0-9]*) echo 'Unexpected Slurm research response' >&2; exit 2 ;; esac
  printf 'Research job: %s (%s CPUs, 4G/CPU, %s, no GPU)\n' "$RESEARCH_ID" "$CPUS" "$LONG_TIME"
fi
RECEIPT="$PROJECT/outputs/cert/submissions/$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
printf '{"smoke_job":"%s","research_job":"%s","research_cpus":%s,"mode":"%s"}\n' \
  "$SMOKE_ID" "$RESEARCH_ID" "$CPUS" "$MODE" > "$RECEIPT"
printf 'Submission receipt: %s\n' "$RECEIPT"
if [ "$RESEARCH_ID" != none ]; then
  printf 'Monitor: bash %s/hpc/monitor.sh %s\n' "$PROJECT" "$RESEARCH_ID"
else
  printf 'Monitor: bash %s/hpc/monitor.sh %s\n' "$PROJECT" "$SMOKE_ID"
fi
