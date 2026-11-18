# Run the new Guard prototype on the university HPC

This runs `gapslice.guard`, a new synthetic research prototype. The completed
inherited-model audit remains unchanged under `outputs/ojcs/`. Read
[the method and novelty boundary](GUARD_METHOD.md) before interpreting results.

## Update and smoke

Use the existing checkout; do not clone over it. Update only when no job from
this project is active and `git status --short` shows no local source changes.
The previously reported audit job has completed. Other projects' jobs can stay
running. Do not cancel them or remove their directories.

On the HPC login node:

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
git pull --ff-only origin ojcs-revision-20261117 &&
bash -l hpc/prepare.sh &&
bash hpc/submit_guard.sh smoke
```

GitHub replaces the Mac-to-HPC source upload for this workflow, as requested.
No archive/results upload is necessary. The exact source-transfer command is
the `git pull --ff-only origin ojcs-revision-20261117` above. It preserves
untracked outputs and refuses non-fast-forward branch updates.

The smoke manifest has 10 tasks: six design/calibration/test evaluations, two
matched no-governor tests and two perfect-radio controls. Eight episodes per
task deliberately cannot qualify a 1% risk requirement. An empty qualified
catalog is an expected scientific outcome in smoke, not a failed pipeline.

The helper invokes this equivalent `sbatch` command after reading `MaxTime`:

```bash
sbatch --parsable --job-name=gs_guard_smoke --partition=shortq \
  --ntasks=4 --time=2-00:00:00 \
  --export=ALL,GS_OJCS_STAGE=guard,GS_OJCS_PRESET=smoke \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/Batch
```

Use the helper as the actual command so the queue's current limit is checked;
do not also run the equivalent example. No job ID is claimed until Slurm
actually returns one.

## Pilot after successful smoke

After inspecting the smoke's exit status and completeness, submit **once**:

```bash
bash /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/submit_guard.sh pilot
```

Pilot has 2,040 tasks, 791,808 complete synthetic episode replays and 42 main
profiles. It includes three target gaps, three channel populations, clustered,
spread and hopped copy patterns, independent design/calibration/test streams,
four seed batches, no-governor ablations and perfect-radio controls. Each
profile/environment has 128 design, 2,048 calibration and 2,048 test episodes.
This is a prototype study; final statistical evaluation will use a new frozen
protocol and fresh data namespace after development.

The corresponding direct submission, if bypassing the helper, is:

```bash
sbatch --parsable --job-name=gs_guard_pilot --partition=shortq \
  --ntasks=40 --time=2-00:00:00 \
  --export=ALL,GS_OJCS_STAGE=guard,GS_OJCS_PRESET=pilot \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/Batch
```

Smoke requests four CPU tasks and 8 GiB total memory; pilot requests 40 CPU
tasks and 80 GiB total memory. Each task uses one CPU with BLAS/solver threads
limited to one. Both use `shortq` with its maximum allowed runtime (previously
reported as 48 hours). No GPU is requested. The helper reads the actual current
limit. Local timings support a pilot substantially shorter than this limit;
actual cluster runtime, aggregate RSS and multi-node behavior remain unverified
until these jobs run. Startup tests and report optimization add overhead.

All paths, environments, dependency installations, caches, temporary files,
logs and results remain under `/home/tariq.qayyum/hpc/GapSlice-OJCS`. Batch
loads `anaconda3` and reuses the project `.venv`; it never writes to the shared
Conda installation. The existing project ownership guard prevents overlapping
environment/campaign mutation.

## Monitor and locate results

Set `JOB` to the returned Slurm ID:

```bash
JOB=REPLACE_WITH_RETURNED_JOB_ID
PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
bash "$PROJECT/hpc/monitor.sh" "$JOB"
squeue -u tariq.qayyum
sacct -j "$JOB" \
  --format=JobID,JobName%24,State,ExitCode,Elapsed,TotalCPU,MaxRSS,AllocTRES%30
sstat -j "$JOB" --allsteps \
  --format=JobID,NTasks,AveCPU,AveRSS,MaxRSS,MaxVMSize
```

For smoke logs:

```bash
tail -f "$PROJECT/logs/gs_guard_smoke_${JOB}.out"
tail -f "$PROJECT/logs/gs_guard_smoke_${JOB}.err"
```

For pilot, replace `gs_guard_smoke` with `gs_guard_pilot`. `sstat` can report no
active steps after completion. CPU utilization is best assessed from final
`sacct`/`seff` accounting; do not interpret broken memory denominators as real
memory usage.

After the job has created its manifest mapping:

```bash
MANIFEST="$(cat "$PROJECT/outputs/guard/jobs/$JOB.manifest")"
CAMPAIGN="$(basename "$MANIFEST" .json)"
BASE="$PROJECT/outputs/guard/$CAMPAIGN"
find "$BASE/workers/$JOB" -maxdepth 1 -name '*.json' -type f | wc -l
find "$BASE/results" -maxdepth 1 -name '*.json' ! -name '*.failed.json' -type f | wc -l
tail -n 2 "$PROJECT/logs/$CAMPAIGN/$JOB"/progress-*.log
grep -RniE 'error|fatal|failed|traceback|oom|killed|timeout' \
  "$PROJECT/logs/$CAMPAIGN/$JOB"
cat "$PROJECT/outputs/job-$JOB/status.json"
cat "$BASE/summary.json"
cat "$BASE/report.md"
```

Worker logs are separate. Partials/final task results are `BASE/results/`;
`BASE/selection.json` records qualification, risk labels, matched test evidence
and checked admission allocations. `BASE/ablations.json` contains matched
controller controls. `BASE/summary.json` is machine-readable execution status;
`BASE/report.md` is the human-readable report. The original manifest and source
hashes are at `MANIFEST`.

## Recovery and verification scope

First inspect the named project's logs/status. Keep the same source/environment
when resuming; do not pull updates while it is active. Rerun the same helper:

```bash
bash /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/submit_guard.sh pilot
```

For smoke recovery, replace `pilot` with `smoke`. The immutable manifest and task
identities skip matching completed tasks, preserve partial evidence and rerun
failed/missing tasks. Required failures propagate to nonzero job status. A code
or dependency change creates a new campaign; no old results are overwritten.
Do not remove a live/unknown project guard or cancel unrelated jobs.

Locally verified checks cover shell syntax, Python compilation, new-method
unit/integrity checks and real local smoke execution. The HPC commands are
prepared but are executed by the project owner. All experiment inputs are
synthetic. Measured-data/testbed validation, calibrated NR decoding, independent
backend agreement, application-grounded tolerances, context classification,
continuous-time safety/string-stability proofs and journal-quality final
comparisons remain open. A successful pilot does not settle those obligations.
