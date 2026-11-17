#!/bin/bash -l
# Run on a login node after cloning. This script submits, but runs no experiments there.
set -euo pipefail
PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
PRESET="${1:-smoke}"
case "$PRESET" in
  smoke) PARTITION=shortq; TASKS=4; NAME=gs_ojcs_smoke ;;
  audit) PARTITION=longq; TASKS=40; NAME=gs_ojcs_audit ;;
  full) PARTITION=longq; TASKS=40; NAME=gs_ojcs_diagfull ;;
  *) echo 'Usage: bash hpc/submit.sh smoke|audit|full' >&2; exit 2 ;;
esac
cd "$PROJECT"
mkdir -p "$PROJECT/logs" "$PROJECT/results" "$PROJECT/outputs" "$PROJECT/figures" "$PROJECT/tmp"
INFO="$(scontrol show partition "$PARTITION" -o)"
LIMIT="$(printf '%s\n' "$INFO" | sed -n 's/.* MaxTime=\([^ ]*\).*/\1/p')"
if [ -z "$LIMIT" ]; then
  echo "ERROR: cannot determine maximum runtime for $PARTITION; inspect scontrol show partition" >&2
  exit 2
fi
case "$LIMIT" in UNLIMITED|INFINITE) LIMIT=23:00:00 ;; esac
for SCRIPT in "$PROJECT/Batch" "$PROJECT"/hpc/*.sh; do
  bash -n "$SCRIPT"
done
printf 'Submitting preset=%s partition=%s tasks=%s cpus/task=1 memory/cpu=2G time=%s GPU=none\n' \
  "$PRESET" "$PARTITION" "$TASKS" "$LIMIT"
sbatch --parsable --job-name="$NAME" --partition="$PARTITION" --ntasks="$TASKS" --time="$LIMIT" \
  --export="ALL,GS_OJCS_PRESET=$PRESET" "$PROJECT/Batch"
