# OJ-CS diagnostic campaigns on Slurm

This branch implements the first diagnostic stage of the
[research revision plan](OJCS_REVISION_PLAN.md). It does not contain a finished
new method or submission-ready results. No cluster execution is claimed by
the presence of these scripts. Use this GitHub-to-HPC workflow; no Mac-side
SSH upload is needed.

## Initial download on the HPC login node

The commands below assume Git already exists. They refuse to clone over an
existing checkout. Nothing installs into shared Conda.

```bash
mkdir -p /home/tariq.qayyum/hpc
git clone --branch ojcs-revision-20261117 --single-branch \
  https://github.com/rtqayyum/GapSlice.git \
  /home/tariq.qayyum/hpc/GapSlice-OJCS
cd /home/tariq.qayyum/hpc/GapSlice-OJCS
mkdir -p logs results outputs figures tmp
bash -l hpc/prepare.sh && bash hpc/submit.sh smoke
```

Submit each stage once using the helper. The direct `sbatch` example below is
an alternative reference, not an additional command to run for the same stage.

For an existing checkout, first inspect `git status --short` and the current
branch. When it has no local source changes, `git pull --ff-only` updates this
branch. Do not replace an existing directory, tracked results or checkpoints.
If Git is unavailable, use `curl` to save the branch tarball inside the new
project directory and extract there, or arrange a project-local Git installation;
do not alter the shared module installation.

Git-free alternative for a new directory (do not use over an existing project):

```bash
PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
if [ -e "$PROJECT" ]; then
  printf 'Project already exists; inspect it before updating.\n'
else
  mkdir -p "$PROJECT"
  curl --fail --location --retry 3 \
    https://codeload.github.com/rtqayyum/GapSlice/tar.gz/refs/heads/ojcs-revision-20261117 \
    -o "$PROJECT/source.tar.gz" && \
  tar -xzf "$PROJECT/source.tar.gz" --strip-components=1 -C "$PROJECT"
fi
```

`hpc/submit.sh` reads the chosen partition's `MaxTime` and submits that maximum
finite walltime. If Slurm reports no finite limit it uses 23 hours. Smoke uses
`shortq`, four tasks and one CPU each. Audit/full use `longq`, 40 tasks, one CPU
each, and 2 GiB requested memory per CPU (80 GiB aggregate for 40 CPUs). No GPU
is requested. The cluster's actual partition limits and node availability must
be checked there. After measuring runtime, a suitably sized shorter queue can
be selected; uncertain production runtimes use longq and resume if interrupted.

The complete entrypoint is `/home/tariq.qayyum/hpc/GapSlice-OJCS/Batch`. Its
direct defaults are audit, longq, 40 CPUs and 23 hours. Using the submission
helper is preferred because it reads the queue limit. Exact equivalent:

```bash
sbatch --job-name=gs_ojcs_audit --partition=longq --ntasks=40 \
  --export=ALL,GS_OJCS_PRESET=audit \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/Batch
```

That direct command keeps the 23-hour fallback in Batch; add `--time` with the
verified queue limit when bypassing the helper.

## Project isolation and bootstrap

Every generated file belongs to `/home/tariq.qayyum/hpc/GapSlice-OJCS`:

- Python dependencies: `.venv/`; pip checks that it is the intended environment.
- Managed Python, when needed: `.python/`; versioned uv binary/installer: `.tools/`.
- Package/cache/bytecode files: `.cache/`; temporary files: `tmp/JOB_ID/`.
- Immutable manifests: `outputs/ojcs/manifests/`.
- New raw records and reports: `outputs/ojcs/CAMPAIGN_ID/`.
- Batch logs: `logs/JOB_NAME_JOB_ID.out` and `.err`.
- Worker logs: `logs/CAMPAIGN_ID/JOB_ID/worker_RANK.out`, `.err` and progress logs.
- Bootstrap/exit status even before a campaign starts: `outputs/job-JOB_ID/status.json` and `status.txt`.

The tracked `results/` inputs remain read-only during diagnostics. Source code,
dependency versions and both descriptor-table hashes identify each campaign.
The batch script loads `anaconda3`, but does not require its default Python to
be modern. Setup reuses a valid project venv or a compatible installed Python.
Otherwise it installs uv 0.13.8 and CPython 3.13.9 under this project, then
creates `.venv/`. The downloaded installer is checked against a pinned SHA256
before execution; unmanaged installation disables shell-profile changes.
All uv/Python caches and installation locations are explicitly project-local.
An incompatible or incomplete `.venv/` is preserved under a timestamped backup
inside the project; a `.venv` symlink is refused rather than modifying its target.

Run `bash -l hpc/prepare.sh` once on the login node before submitting. This
downloads/interprets dependencies only; it runs no scientific simulations.
It installs `requirements-hpc.txt` into `.venv/`, requires binary wheels so it
does not build large scientific packages on the login node, and checks imports.
It never installs into `/cm/shared/apps/anaconda3`. Its log is
`logs/prepare-TIMESTAMP-PID.log`; machine-readable runtime information is
`outputs/setup/runtime.json` and the installed versions are in
`outputs/setup/environment.txt`. Batch reuses the prepared environment, allowing
compute nodes to run without repeating downloads. Outbound access and compatible
Linux wheels must be available during preparation; failures are shown before a
job is submitted when the preparation and submission commands are joined by `&&`.
No Git is needed by Batch.

Preparation also runs the runtime and project-guard checks before submission;
scientific simulations stay in the batch job. Compatible interpreter aliases
are resolved to their base installation and standard Unix venv symlinks are
used, preserving the standalone interpreter's library lookup. Only executables
inside the project environment link to their base interpreter; the `.venv`
directory itself remains a real project-owned directory.

To explicitly request the managed interpreter on a fresh setup, use
`GS_OJCS_MANAGED_PYTHON=1 bash -l hpc/prepare.sh`. An existing compatible project
venv is still reused. On x86-64, managed Python targets baseline x86_64 rather
than an optimized CPU tier that might differ between login and compute nodes.

One project guard prevents simultaneous submissions from changing the same
environment or campaign outputs. It uses directory creation at
`outputs/ojcs/.campaign.guard`, records job/host/PID ownership, and requires no
`flock` support from the shared filesystem. Normal and handled failure exits
release only the current owner's guard. A pre-existing guard is reported with
its metadata, not assumed to prove a currently running job. Filesystem creation
errors have a separate diagnostic. The old `.campaign.lock` file is unused and
can be left in place; deleting a kernel-lock file is not a recovery procedure.

The guard does not affect another project. Worker
BLAS/OpenMP thread counts are one, so 40 tasks do not each start 40 threads.
Parallel work launches with `srun`, not on the login node.

## After smoke succeeds

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS
bash hpc/submit.sh audit
```

Audit has 2,004 configurations. Keep its reports for model decisions. The full
diagnostic preset has 25,308 configurations and is available as
`bash hpc/submit.sh full`, but inspect audit results and runtime first. Neither
preset evaluates the future rebuilt method. See the plan for final experiments.

## Monitor a known job

Replace `123456` with the actual job ID printed by sbatch.

```bash
squeue -u tariq.qayyum
sacct -j 123456 --format=JobID,JobName,State,ExitCode,Elapsed,TotalCPU,MaxRSS,AllocTRES%30
bash /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/monitor.sh 123456
tail -f /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/gs_ojcs_audit_123456.out
tail -f /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/gs_ojcs_audit_123456.err
sstat -j 123456 --allsteps --format=JobID,NTasks,AveCPU,AveRSS,MaxRSS,MaxVMSize
grep -RniE 'error|fatal|failed|traceback|oom|killed|timeout' \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/logs/
```

The monitor reports completed worker records, complete and failed experiments,
recent progress, task CPU accounting and memory. `seff` is used when installed;
its efficiency estimates are most useful after completion. Running-step CPU
times are not instantaneous utilization percentages. Slurm accounting may lag.
The monitor uses the manifest associated with the specified job rather than
mixing results from a different campaign. Before Batch creates that mapping,
only scheduler/setup information will be available.

## Results and recovery

Each task writes a complete JSON record by atomic replacement. Interrupted
tasks are rerun; completed matching tasks are preserved. Any required task
failure or missing result makes the final Batch status nonzero. Separate
failed-task records contain tracebacks. Do not manually relabel them complete.

After a failure, fix the environment or documented cause and resubmit the same
preset with unchanged code, dependencies and table inputs:

```bash
bash /home/tariq.qayyum/hpc/GapSlice-OJCS/hpc/submit.sh audit
```

Matching complete records are skipped. A source, environment or table change
creates a new campaign identity rather than overwriting old evidence. Batch
does not cancel any job. Do not run `scancel` on a job without first verifying
its identity as belonging to this project.

The environment identity includes OS, architecture, Python implementation,
compiler and base-installation path as well as library versions, so results
from a Conda interpreter are not silently reused as a fresh managed-runtime run.

An unhandled kill or node failure can leave the directory guard behind. If that
happens, inspect `outputs/ojcs/.campaign.guard/owner` and check the recorded job
with `squeue` and `sacct`. Do not infer its status from an old PID on a different
node. Guards are never reclaimed automatically. Only after confirming the owner
is terminal and that no other campaign for this project is starting/running,
preserve the abandoned guard by moving it to a unique archive name inside
`outputs/ojcs/`, then resubmit once. No other project's files or jobs need changes.
For a preparation guard with `job_id=local`, check the recorded host/PID on that
same login host instead of looking up a nonexistent Slurm job.

For a partial report, read the relevant job's manifest path:

```bash
cat /home/tariq.qayyum/hpc/GapSlice-OJCS/outputs/ojcs/jobs/123456.manifest
```

Then, in the same loaded module/project environment, run:

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS
export GS_OJCS_PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS
export GS_OJCS_ATTEMPT=123456
source hpc/environment.sh
module load anaconda3
/home/tariq.qayyum/hpc/GapSlice-OJCS/.venv/bin/python -m gapslice.revision.campaign report \
  --manifest /ABSOLUTE/PATH/PRINTED/ABOVE.json --allow-incomplete
```

Final/partial report paths are `outputs/ojcs/CAMPAIGN_ID/report.md`,
`summary.json`, `metrics.csv` and `results/*.json`. Read `summary.json` for
complete/failed/pending counts; a report file alone does not mean a run passed.
Both diagnostics and inherited data are synthetic. Supplied cluster logs have
confirmed successful project-local Linux dependency preparation; successful
worker execution and full campaign completion still require a passing smoke job.
