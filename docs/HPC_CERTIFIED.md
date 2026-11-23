# GapSlice-Cert: full CPU research study

This package is the complete redesign entrypoint. It preserves all old Guard
and diagnostic code/results. The scientific scope and conditional arguments
are in [CERTIFIED_PROOFS.md](CERTIFIED_PROOFS.md). Better performance and journal
acceptance remain empirical/editorial questions. No external measured data are
included. Nothing registers Red Hat systems or touches another project.

## Execute on the university login node

```bash
module load slurm
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
git pull --ff-only origin ojcs-revision-20261117 &&
bash -l hpc/prepare.sh &&
bash -l hpc/run_certified.sh research
```

The launcher checks `sbatch --test-only` for both allocations before submitting.
It prints the actual two job IDs and stores a submission receipt. It submits
`gs_cert_smoke` (4 CPUs, 2 GiB/CPU, shortq), then `gs_cert_research` (160 CPUs,
4 GiB/CPU, longq), dependent on smoke success. Both use the **current partition
MaxTime reported by scontrol** (previously shortq 2 days, longq 20 days),
1 CPU/task and no GPU. These are maximum reservations, not predicted runtimes.
Slurm may queue or reject the request based on account/QOS limits. Account
limits, disk quota and cluster speed have not been inspected remotely.
`sbatch --test-only` validates scheduler arguments and estimates scheduling;
it does not execute application code ([Slurm documentation](https://slurm.schedmd.com/sbatch.html)).

To change CPU parallelism without changing the scientific protocol:

```bash
GS_CERT_CPUS=320 bash -l /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/run_certified.sh research
```

160 is the default to limit filesystem pressure while making independent CPU
replays parallel. No CUDA workload exists. Do not keep increasing workers
without checking CPU efficiency, shared-filesystem throughput and account limits.

Exact underlying research submission, if submitting individually is necessary:

```bash
sbatch --job-name=gs_cert_research --partition=longq \
  --ntasks=160 --cpus-per-task=1 --mem-per-cpu=4G --time=20-00:00:00 \
  --chdir=/home/tariq.qayyum/hpc/GapSlice-OJCS \
  --export=ALL,GS_OJCS_STAGE=certified,GS_OJCS_PRESET=research \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/Batch
```

Prefer the launcher: it queries the actual queue maximum rather than hardcoding
20 days, preflights allocations, and automatically gates research on smoke.
Do not also submit Batch with its old default diagnostic stage.

## What runs

The frozen protocol spans 72 contract groups: N=3/5/7 trucks, requested
headway 0.6/0.8/1.0/1.2 seconds, capacity 51/106 PRBs, payload 300/600/1200 bytes.
Initial headway is 1.5 seconds. Every controller uses the same actuator limits,
bounded sensors, physical plant, reference governor and safety filter.

* **151,668 design candidates**, including fused/hold/radar predictor modes,
  three gain tuples, radio-free operation, feasible serial/parallel schedules,
  phase offsets 0/20/40/60/80 ms, PRB widths 10 through100 where feasible,
  and 1/2/4 copies with clustered/spread/hopped geometry.
* **29,120,256 design episode replays**, 64/candidate/environment over nominal,
  correlated and blocked synthetic channels. These choose gains and candidates.
* Freeze one gain per contract/controller. Keep the design-best parallel and
  serial option for each phase/domain, plus the zero-radio option. At most
  **4,536** candidates survive; duplicates across domains reduce the actual count.
* For every frozen candidate/environment: **32,768 calibration +32,768 fresh
  held-out episodes**, in fixed storage shards of 2,048 (numerical microbatches of128). At most **891,813,888** combined
  replays. Test data never select the bank, risk label or admission policy.
* Calibration-based representative no-shield/perfect-radio ablations and harder
  plant shifts (108 km/h slow actuators and 60 km/h alternating actuator lags,
  hard -6 m/s² braking). Matched ablations use exactly the first held-out batch's
  seed, dimensions, source phase and batch size; shifts are labeled separately.
* Multi-tenant admissions for 4/8/16/32 requests at both capacities and declared
  domains; fused, hold, radar, parallel-only and synchronous-only comparisons;
  greedy and MILP packing; exact independent integer relaxation bounds.

Episodes are 40-second nonlinear replays at 2 ms physics/10 ms control ticks.
This is a heavy synthetic study, not a request to repeat the old 2,040-cell
pilot. The maximum replay count includes zero-radio repeats across payload/cap
contracts; they retain comparable per-contract tuning budgets and provenance.
A future efficiency improvement may reuse them only with explicit provenance.

## Resources and storage

Actual local development timing: a 64-episode, N=5, blocked, 40-second replay
took about4.8 seconds on this Mac. An N=7, 2,048-episode replay took237 seconds and peaked near808 MiB; a128-episode microbatch peaked near231 MiB. This is not a cluster runtime estimate;
large-batch cost, memory, interconnect/filesystem and node CPU differ. The job
records each task's CPU/wall time and peak process RSS. Plan for a multi-day
160-CPU run and potentially tens of thousands of core-hours. It may need a
resume if it reaches the queue limit. No completion-time promise is made.

Allow approximately **200 GiB free and at least 2.5 million free inodes**, with
quota checked separately. Actual compression/selection changes storage use.
There are at most217,728 calibration shards and the same test shard count,
plus455,004 design shards; each has a JSON commit marker and compressed NPZ.
Result paths are split into256 hash-prefix directories per stage; directory metadata can still be substantial. All generated files remain
inside `/home/tariq.qayyum/hpc/GapSlice-OJCS/`, including .venv and caches.
The shared Anaconda installation is loaded read-only and is never modified.

```bash
df -h /home/tariq.qayyum/hpc/GapSlice-OJCS
df -i /home/tariq.qayyum/hpc/GapSlice-OJCS
quota -s
```

`df` capacity is not an account quota check. There is no automatic deletion or
resubmission loop. Partial results survive timeouts and failures.

## Monitor and recover

### Resume a running study with more CPUs

The standalone `scripts/scale_certified.py` helper stages a replacement before
interrupting the old computation. Adding this helper, its `test_hpc_scaling.py`
tests and documentation does not change the frozen scientific/execution
fingerprint. That equality is checked locally before this update is published;
the helper also verifies the actual HPC study's source/runtime before cancelling.
No source, dependency, scientific protocol or completed result is modified.

For the current job, after the successful1280-CPU scheduler preflight:

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
git pull --ff-only origin ojcs-revision-20261117 &&
/home/tariq.qayyum/hpc/GapSlice-OJCS/.venv/bin/python \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/scripts/scale_certified.py \
  --from-job 3098836 --cpus 1280
```

The helper verifies the old job's exact ID, owner, job name, project directory,
study signature and guard ownership. It checks the projected running CPU count
against1600 and queries longq's current maximum time. It submits the replacement
**held**, with `afterany:3098836`, then records its ID under
`outputs/cert/submissions/scale-3098836-to-NEW_JOB.json`. Only after successful
submission does it cancel **3098836**, using `scancel --full` so the batch shell
can handle its cleanup trap. It waits up to60 seconds for termination/accounting
and requires the project guard to be absent before releasing the held job.

Preflight/submission/source/identity failures leave the old computation running.
If termination is slow or a guard remains, the replacement stays held; the
helper reports its ID and does **not** remove the guard. Inspect the output
before manually releasing anything. Other projects' jobs are never cancelled.
Completed result shards are verified and reused; interrupted shards repeat.
The resumed study uses the new worker count without changing its random seeds.

The current4GiB/CPU setting requests5TiB for1280 CPUs. The CPU count is a
request, not a guarantee of immediate allocation or linear speedup. The
user-provided successful preflight estimated2026-11-24T18:04:18; this is not a
reserved start time. At the supplied snapshot, other projects used162 CPUs;
replacing160 with1280 yields1442 total, below1600. The helper rechecks usage.

Fifteen mocked scheduler tests cover operation ordering, result preservation,
rejected requests, wrong identities, changed source, quota violations and
held-job behavior on incomplete cleanup, plus explicit guard recovery. These are local control-flow tests,
not a1280-worker performance benchmark. The application has also completed a
local2-to-4-worker resume with all24 raw shards unchanged.

### Recover the existing held replacement after a stale guard

The actual handover stopped3098836 but its guard remained, so3111745 was
correctly left held. Use this explicit recovery mode for that exact pair:

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
git pull --ff-only origin ojcs-revision-20261117 &&
/home/tariq.qayyum/hpc/GapSlice-OJCS/.venv/bin/python \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/scripts/scale_certified.py \
  --from-job 3098836 --replacement-job 3111745
```

It verifies the saved handover receipt, unchanged frozen study, replacement
identity/owner/CPU count and held status. Slurm accounting and the live queue
must both confirm that the old job ended. A remaining guard must name exactly
that terminated job; ownership/termination are rechecked before the guard is
renamed into `outputs/cert/guard-recovery/`. The entire directory and its owner
record are preserved. The command then releases the **existing** replacement.
It neither submits nor cancels any job and never edits scientific results.
An active old job, unexpected guard owner or non-held replacement is rejected.
This recovery-only helper update also leaves the scientific/execution
fingerprint unchanged. Local recovery tests pass; actual cluster recovery is
not claimed until the user runs the command and checks its result.

If smoke job3098812 failed only in temporary proof-table cleanup, pull the
mapping-lifetime fix before retrying. All17 functional checks passed in that
attempt; the simulation campaign had not started. Job3098813 belongs to this
project and has an impossible afterok dependency on that failed smoke. Replace
that specific stale submission with a fresh smoke-gated pair:

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
git pull --ff-only origin ojcs-revision-20261117 &&
bash -l hpc/prepare.sh &&
scancel 3098813 &&
bash -l /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/run_certified.sh research
```

This cancels only the identified, never-started project job; it does not touch
the user's other jobs. If3098813 was already removed, proceed with the launcher
after the successful pull/preparation. See CERTIFIED_VERIFICATION.md for the
failure evidence and local checks. Current queue estimates remain unverified
until the new submission is inspected.

Replace JOB_ID with the **research job ID printed by the launcher**:

```bash
bash /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/monitor.sh JOB_ID
squeue -u tariq.qayyum
sacct -j JOB_ID --format=JobID,JobName%24,State,ExitCode,Elapsed,TotalCPU,MaxRSS,AllocTRES%30
sstat -j JOB_ID --allsteps --format=JobID,NTasks,AveCPU,AveRSS,MaxRSS,MaxVMSize
tail -f /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/gs_cert_research_JOB_ID.out
tail -f /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/gs_cert_research_JOB_ID.err
```

`monitor.sh` shows per-stage completed/failed task counts, worker records and
recent progress. Task episode counts are declared in each manifest. After a
stage finishes, summary.json records its expected/complete counts. The final
summary.json records held-out episode counts. Use `seff JOB_ID` for post-job
CPU/memory efficiency where available. `sstat` needs a currently running step.

```bash
STUDY="$(cat /home/tariq.qayyum/hpc/GapSlice-OJCS/outputs/cert/jobs/JOB_ID.study)"
find "$STUDY" -name '*.failed.json' -print
rg -n 'FAILED|Traceback|certificate.*violated|ERROR|oom|killed' \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/"$(basename "$STUDY")"/
```

Recovery, after the failed/time-limited job has ended, with the **same source
commit, Python environment and protocol**:

```bash
bash -l /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/run_certified.sh resume
```

This submits only the research job. It checks existing raw-data hashes and
resumes unfinished tasks. Successful results are never overwritten. Orphan
NPZ/failed attempt records are preserved. Any required-task failure exits
nonzero; a scientific bound breach aborts rather than becoming a successful
count. If smoke fails, research stays blocked by afterok; inspect the error
before using resume. No script cancels jobs. Identify this project's explicit
job IDs yourself before canceling any obsolete pending dependency.

Source/runtime/protocol changes create a new immutable study ID; they cannot
silently reuse old scientific results. Do not pull or edit source during a run.
Revising after held-out inspection requires a fresh final namespace and review.

## Recovery from the 768-rank launch failure (job 3111745)

The supplied logs show two failures: Slurm could not connect task I/O for
ranks 30–90, and rank 475 on cn171 raised `FileNotFoundError` when renaming
an optional worker telemetry file. Slurm then terminated the worker step.
The base driver subsequently scanned cached results, leaving the batch job
apparently running without simulation workers. The soft/hard open-file limits
were both 131072. These observations do not establish the underlying network
or filesystem cause; they do not demonstrate a corrupt scientific result.
The user has issued `scancel --full --quiet 3111745`.

Use the recorded runtime adapter for this stopped study:

```bash
module load slurm
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
git pull --ff-only origin ojcs-revision-20261117 &&
/home/tariq.qayyum/hpc/GapSlice-OJCS/.venv/bin/python \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/scripts/certified_runtime.py submit \
  --from-job 3111745 --cpus 768 --per-node 64
```

This checks the old job has ended in both accounting and the live queue,
verifies its owner/name, mapping and frozen source/runtime, checks the actual
`limit` QoS CPU allowance and current user CPU usage, and runs `sbatch --test-only`.
It then submits one HELD job and records a receipt. Only a guard owned by the
verified terminated old job can be archived before the new job is released.
No job is canceled. A different or live guard owner is rejected. If cleanup is
not yet complete, wait for Slurm to finish it and rerun; there is no new job
until these checks pass. If the tool prints a HELD replacement ID before an
error, use its printed recovery command instead of submitting another job.

The scheduler request is 12 nodes, 64 single-CPU ranks per node, 768 CPUs,
4 GiB/CPU (3 TiB total), the queried maximum `longq` walltime (currently
20 days), and no GPU. The actual QoS limit observed on this cluster is
**1000 CPUs/user**, not the originally stated 1600. With 162 other running
CPUs the projected total is 930. The tool recomputes this at submission;
other pending jobs can still affect scheduling. Exactly 12 fully available
64-CPU nodes may queue differently from the previous scattered allocation.
There is no promised queue start time or measured 768-CPU speedup yet.

Before any simulation, a five-minute Slurm step tests all 768 ranks, the same
compact placement and per-worker stdout/stderr routing, and shared-filesystem
write/fsync/rename/read. Every rank and host/local-rank count must be present.
Probe failure exits nonzero before scientific work; inspect its logs rather
than retrying a multi-day run blindly. A successful probe is a point-in-time
check and cannot guarantee the network/filesystem will stay healthy.

The adapter also:

- Retries optional worker telemetry writes three times. If all retries fail,
  it logs a warning and continues. Scientific result JSON/NPZ writes, checksums,
  task failures, manifests, qualification and report commits remain required.
- Exits immediately on a failed `srun` step, before scanning hundreds of
  thousands of cached records. Successfully committed results remain available.
- Avoids relaunching a completed design/calibration/test stage when its existing
  successful summary matches. Before any subsequent scientific use, the original
  aggregator revalidates every task identity and raw NPZ digest. Missing/altered
  results fail the job. Nothing is accepted solely from the summary.
- Prefetches original result validation with eight bounded I/O threads in the
  coordinator. The original aggregator performs its original additions in
  manifest order; scientific reductions, selection rules and RNG streams do not
  change. Worker task assignment remains the original rank-independent striding.

`scripts/certified_runtime.py` is deliberately outside the base source hash.
**This is a changed execution adapter**, recorded separately rather than hidden
behind the original fingerprint. Submission snapshots its full source, a
generated effective Batch and a spec with their SHA-256 hashes under
`outputs/cert/runtime/OLD_JOB-TIMESTAMP/`. The generated Batch changes only the
certified dispatch to the snapshotted adapter; the tracked `Batch`, all
`gapslice/` code, frozen tests and proof document remain byte-identical. The
adapter checks the original source/runtime and frozen study in coordinator and
workers. Do not edit or pull again while it runs.

New job IDs, resources, base fingerprint, adapter hash, effective Batch hash,
probe and stage outcomes are linked under:

```text
outputs/cert/submissions/scale-3111745-to-NEW_JOB.json
outputs/cert/studies/cert-research-16130d0ca159e816/runtime/NEW_JOB/provenance.json
outputs/cert/studies/cert-research-16130d0ca159e816/runtime/NEW_JOB/probe.json
outputs/cert/studies/cert-research-16130d0ca159e816/runtime/NEW_JOB/probe/probe_RANK.err
outputs/cert/studies/cert-research-16130d0ca159e816/runtime/NEW_JOB/failure.json
```

`failure.json` exists only if a launch/worker failure was recorded. Other errors
are also recorded in `provenance.json` and the main job `.err`. Probe records
are operational checks, not scientific experiment results. On success, transfer
both `analysis_bundle.tar.gz` and `runtime/NEW_JOB/runtime_bundle.tar.gz` for
complete scientific and changed-execution provenance. The latter contains the
exact adapter, effective Batch, spec, provenance and successful probe summary.

Monitor with the NEW_JOB ID printed by the command:

```bash
squeue -j NEW_JOB -o '%.18i %.24j %.10T %.8C %.14M %.14L %R'
sacct -j NEW_JOB --format=JobID,JobName%24,State,ExitCode,Elapsed,TotalCPU,AllocCPUS,MaxRSS
sstat -j NEW_JOB --allsteps --format=JobID,NTasks,AveCPU,AveRSS,MaxRSS,MaxVMSize
tail -n 80 /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/gs_cert_research_NEW_JOB.out \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/gs_cert_research_NEW_JOB.err
```

Expect `PROBE PASSED ranks=768 hosts=12`, then completed-design reuse and
`REVALIDATE stage=design` progress before calibration starts. This revalidation
is I/O work and can take time without busy simulation ranks. The original
`monitor.sh` can be slow because it enumerates all existing results; use the
main log for quick checks during launch/revalidation. Optional telemetry can be
missing, so raw committed results determine completion. Count **fresh COMPLETE
events**, excluding RESUME, over two snapshots to estimate throughput after
calibration starts; processed telemetry includes reused work and is unsuitable
as a fresh-work rate. No ETA is measured before fresh work is observed.

If a new job later fails/time-limits, preserve its ID and use this adapter's
`submit --from-job NEW_JOB --cpus 768 --per-node 64` after termination. It resumes
the same study and archives only that terminated job's guard if necessary.
If Slurm I/O errors repeat during the probe, send the job ID, affected hosts
and rank logs to cluster support. Node exclusions are available only as an
explicit optional `--exclude cnNNN,cnMMM`; the software does not infer a faulty
node or change scientific tasks to make a launch pass.

Local verification on 23 November 2026 passed 16 adapter tests and 66 existing
launch/scaling/scientific tests. The Slurm submission tests use mocks only.
A freshly computed synthetic smoke run completed 24 tasks / 112 episodes;
all scientific task summaries and all 150 stored vectors exactly matched the
unchanged original pipeline. A second local pass changed the rank count from
two to four and preserved the hashes and modification times of all 48 result
JSON/NPZ files. Bash syntax, Python compilation and the original base source /
execution fingerprint checks passed. The only subsequent adapter changes
affected submission logging and canonical-path checking, not the pipeline.
Neither check establishes successful cluster operation or research results
at 768 ranks. The effective adapter is an operational recovery, not a new
scientific method or strengthened theorem.

## Read-only progress and sampled ETA

Use `scripts/certified_progress.py` for a compact status snapshot without
enumerating every raw-result file:

```bash
/home/tariq.qayyum/hpc/GapSlice-OJCS/.venv/bin/python \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/scripts/certified_progress.py \
  --job 3111761 --sample 60
```

It prints live/accounting state (including failure exit codes and allocated
nodes), batch/probe/failure status when present, main-log tails, deduplicated
logged completions across all attempts, and fresh/reused counts for this job.
It reads the small frozen protocol prefix and selection to obtain the exact
calibration/test totals; it does not load the full candidate bank or import
the simulator. Logged completion is progress evidence, not a replacement for
the pipeline's required raw-data checksums and final validation.

For a RUNNING job, it takes a second sample after 60 seconds and estimates
remaining main-replay time from **new COMPLETE task IDs only**. RESUME events
and worker processed counters never inflate this rate. At least ten fresh
main-task completions and a 30-second observation window are required. A failed
or unconfirmed job, unresolved task failure, or insufficient progress produces
no numerical ETA. `--sample 300` uses a longer window; `--sample 0` skips sampling.
The snapshot prints immediately before waiting. A short-window extrapolation
assumes future throughput is similar and does not include diagnostics, result
revalidation, allocation or report generation; stragglers can extend it.

The helper writes no files, changes no jobs and uses no simulator workers.
It is outside the frozen source/execution fingerprint, as are its
`tests/test_hpc_progress.py` checks. Installing only this helper/tests/documentation
commit while the snapshotted runtime is active leaves its source/runtime
identity unchanged. Five local tests cover cross-attempt deduplication,
reused/fresh accounting, partial log lines, ETA arithmetic and failed-job
reporting. HPC progress or an ETA is not claimed until the command is run there.

## Results and transfer

For a completed job:

```bash
STUDY="$(cat /home/tariq.qayyum/hpc/GapSlice-OJCS/outputs/cert/jobs/JOB_ID.study)"
cat "$STUDY/summary.json"
cat "$STUDY/report.md"
printf '%s\n' "$STUDY/analysis_bundle.tar.gz"
```

The small bundle includes protocol/source provenance, design selection,
qualification, test-cell counts, diagnostics, allocations, proof checks and
report. Full per-episode vectors remain under each phase's `results/`.
`outputs/cert/last_study.txt` points to the latest launched study.

The requested source upload is GitHub based; `git pull --ff-only` above is the
exact HPC download command after this branch is pushed. An alternative explicit
Mac source upload, excluding generated artifacts, is:

```bash
rsync -az --progress --exclude='.git/' --exclude='.venv/' --exclude='.tools/' \
  --exclude='.cache/' --exclude='.python/' --exclude='logs/' --exclude='results/' \
  --exclude='outputs/' --exclude='tmp/' --exclude='figures/' \
  /Users/rana/Documents/GapSlice-Trucks/v4_ojcs/repository/ \
  tariq.qayyum@10.90.24.15:/home/tariq.qayyum/hpc/GapSlice-OJCS/
```

Prefer GitHub to maintain source provenance. Existing tracked legacy result
inputs already present in the checkout are required by source fingerprinting;
do not exclude them from an initial clone. Never overwrite HPC outputs by rsync.

## Execution evidence

Local unit/proof checks and a real full smoke pipeline are executed on the Mac.
They exercise synthetic episodes, not real truck/channel measurements. Mock
Slurm tests check submission arguments/dependencies without submitting jobs.
The new research job and its Slurm resource compatibility remain unexecuted
until the user runs the command; earlier successful Guard jobs do not validate
this new implementation. Numerical verification supports, and does not replace,
the conditional mathematical arguments. External calibration, faithful additional
published baselines and independent theorem review remain publication work.
