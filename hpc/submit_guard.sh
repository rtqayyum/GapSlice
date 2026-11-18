#!/bin/bash -l
# Submit the new synthetic research prototype, not the inherited diagnostic grid.
set -euo pipefail
PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
PRESET="${1:-smoke}"
case "$PRESET" in
  smoke) TASKS=4; NAME=gs_guard_smoke ;;
  pilot) TASKS=40; NAME=gs_guard_pilot ;;
  *) echo 'Usage: bash hpc/submit_guard.sh smoke|pilot' >&2; exit 2 ;;
esac
PARTITION=shortq
cd "$PROJECT"
mkdir -p "$PROJECT/logs" "$PROJECT/results" "$PROJECT/outputs/guard" "$PROJECT/figures" "$PROJECT/tmp"
INFO="$(scontrol show partition "$PARTITION" -o)"
LIMIT="$(printf '%s\n' "$INFO" | sed -n 's/.* MaxTime=\([^ ]*\).*/\1/p')"
if [ -z "$LIMIT" ]; then echo 'ERROR: cannot determine shortq time limit' >&2; exit 2; fi
case "$LIMIT" in UNLIMITED|INFINITE) LIMIT=23:00:00 ;; esac
for SCRIPT in "$PROJECT/Batch" "$PROJECT"/hpc/*.sh; do bash -n "$SCRIPT"; done
printf 'Submitting synthetic Guard %s: queue=%s tasks=%s cpus/task=1 memory/cpu=2G time=%s GPU=none\n' \
  "$PRESET" "$PARTITION" "$TASKS" "$LIMIT"
sbatch --parsable --job-name="$NAME" --partition="$PARTITION" --ntasks="$TASKS" --time="$LIMIT" \
  --export="ALL,GS_OJCS_STAGE=guard,GS_OJCS_PRESET=$PRESET" "$PROJECT/Batch"
