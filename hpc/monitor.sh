#!/bin/bash
set -euo pipefail
PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
JOB="${1:?Usage: bash hpc/monitor.sh JOB_ID}"
case "$JOB" in *[!0-9]*) echo 'Expected a numeric Slurm job ID' >&2; exit 2 ;; esac
if ! squeue -j "$JOB" -o '%.18i %.22j %.10P %.8T %.10M %.6C %R'; then
  printf 'Live queue lookup unavailable for job %s; continuing to accounting and stored results.\n' "$JOB"
fi
if ! sacct -j "$JOB" --format=JobID,JobName,State,ExitCode,Elapsed,TotalCPU,AllocCPUS,MaxRSS,AllocTRES%30; then
  printf 'Accounting lookup unavailable for job %s; continuing to stored results.\n' "$JOB"
fi
# Batch may be idle while srun steps are active, so inspect both batch and worker steps.
sstat -j "$JOB" --allsteps --format=JobID,NTasks,AveCPU,AveCPUFreq,AveRSS,MaxRSS,MaxVMSize || true
if command -v seff >/dev/null 2>&1; then seff "$JOB" || true; fi
for STAGE in ojcs guard; do
if [ -f "$PROJECT/outputs/$STAGE/jobs/$JOB.manifest" ]; then
  MANIFEST="$(cat "$PROJECT/outputs/$STAGE/jobs/$JOB.manifest")"
  CAMPAIGN="$(basename "$MANIFEST" .json)"
  BASE="$PROJECT/outputs/$STAGE/$CAMPAIGN"
  printf 'Campaign for this job: %s\n' "$CAMPAIGN"
  printf 'Worker records: '
  find "$BASE/workers/$JOB" -maxdepth 1 -name '*.json' -type f 2>/dev/null | wc -l || true
  printf 'Complete experiment records: '
  find "$BASE/results" -maxdepth 1 -name '*.json' ! -name '*.failed.json' -type f 2>/dev/null | wc -l || true
  printf 'Failed experiment records: '
  find "$BASE/results" -maxdepth 1 -name '*.failed.json' -type f 2>/dev/null | wc -l || true
  tail -n 2 "$PROJECT/logs/$CAMPAIGN/$JOB"/progress-*.log 2>/dev/null || true
  printf 'Partial/final results: %s\nReport: %s\n' "$BASE/results" "$BASE/report.md"
fi
done
