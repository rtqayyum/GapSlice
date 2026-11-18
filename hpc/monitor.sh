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
if [ -f "$PROJECT/outputs/cert/jobs/$JOB.study" ]; then
  STUDY="$(cat "$PROJECT/outputs/cert/jobs/$JOB.study")"
  case "$STUDY" in "$PROJECT"/outputs/cert/studies/cert-*) ;; *) echo 'Invalid study path' >&2; exit 2 ;; esac
  printf 'Certified redesign study: %s\n' "$STUDY"
  for PHASE in design calibration test diagnostics allocation; do
    BASE="$STUDY/$PHASE"
    if [ -d "$BASE/results" ]; then
      printf '%s complete tasks: ' "$PHASE"
      find "$BASE/results" -maxdepth 2 -type f -name '*.json' ! -name '*.failed.json' | wc -l
      printf '%s failed tasks: ' "$PHASE"
      find "$BASE/results" -maxdepth 2 -type f -name '*.failed.json' | wc -l
      printf '%s worker records: ' "$PHASE"
      find "$BASE/workers/$JOB" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l || true
      "$PROJECT/.venv/bin/python" - "$BASE/workers/$JOB" <<'PY'
import json,sys
from pathlib import Path
records=[json.loads(p.read_text()) for p in Path(sys.argv[1]).glob('*.json')]
print('Worker telemetry: finished=%s processed_shards=%s episode_replays=%s' % (
    sum(bool(x.get('finished')) for x in records),sum(x.get('processed',0) for x in records),
    sum(x.get('completed_episodes',0) for x in records)))
PY
      if [ -f "$BASE/summary.json" ]; then cat "$BASE/summary.json"; fi
    fi
  done
  tail -n 1 "$PROJECT/logs/$(basename "$STUDY")/$JOB"/*/progress-*.log 2>/dev/null || true
  printf 'Report: %s/report.md\nSmall results bundle: %s/analysis_bundle.tar.gz\n' "$STUDY" "$STUDY"
fi
