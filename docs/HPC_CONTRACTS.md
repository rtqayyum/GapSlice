# Fresh contract study on the university HPC

Project: `/home/tariq.qayyum/hpc/GapSlice-OJCS`, existing branch
`ojcs-revision-20261117`. User runs commands on HPC; no SSH automation is used.
Completed certified studies remain unchanged. The contract environment is a
separate `.venv-contract`; dependencies and all caches/temporary files stay in
this project. No shared Conda installation or another project is modified.

## Pull, prepare, and start

```bash
module load slurm
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
git pull --ff-only origin ojcs-revision-20261117 &&
bash -l hpc/contracts/prepare.sh &&
.venv-contract/bin/python -m contractlab.hpc submit pilot
```

Pilot: 32 CPU ranks on one node, 4G/CPU, shortq, queried queue maximum walltime
(currently 2 days), no GPU. This pilot runs the external software checks, all
pipeline stages, resume-capable shard commits and allocation/report/bundling.
Low pilot sample sizes are for checking execution, not qualification evidence.
Optional smaller launch: replace `pilot` with `smoke` (4 CPUs, shortq).

After the pilot reports COMPLETED, launch the research run:

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS &&
.venv-contract/bin/python -m contractlab.hpc submit research
```

Research: **480 CPU ranks = 15 nodes x 32 ranks/node**, one CPU/rank,
4G/CPU (1,920 GiB requested across all nodes), longq, queried maximum walltime
(currently 20 days), **no GPU**. No speedup or finish date is promised before
the pilot measures throughput. Checkpointed shards permit continuation if a
queue limit, cluster problem or unexpected runtime prevents completion.
Previously unreliable nodes cn164/cn171 are excluded. The launcher reads the
actual `limit` QoS allowance and counts other projects' current running CPUs;
it does not assume the historical 1,600-CPU figure. With a 1,000-CPU user limit,
there must currently be at least 480 CPUs of remaining allowance.

The launcher runs `sbatch --test-only`, submits HELD, writes a receipt, then
releases that exact job. Its effective command is:

```bash
sbatch --job-name=gs_contract_research --partition=longq --qos=limit \
  --nodes=15 --ntasks=480 --ntasks-per-node=32 --cpus-per-task=1 \
  --distribution=block:block --mem-per-cpu=4G --time=20-00:00:00 \
  --exclude=cn164,cn171 --chdir=/home/tariq.qayyum/hpc/GapSlice-OJCS \
  --export=ALL,GS_CONTRACT_PRESET=research \
  /home/tariq.qayyum/hpc/GapSlice-OJCS/BatchContracts
```

Use the Python launcher: it applies the pilot, dependency, ownership, quota and
duplicate-job checks and queries MaxTime rather than assuming the example value.
No runtime dependency installation happens in the 480-rank job.
The first srun launches every requested rank and delays one rank/node 40 seconds.
Every srun explicitly sets `--wait=0 --kill-on-bad-exit=1`, so successful peers
cannot trigger the former 30-second cancellation. Per-rank probe files and host
counts are preserved. Worker sizing comes from Slurm, never a stale 768 constant.

## Monitor

Set the numeric ID printed by the submission command:

```bash
JOB_ID=1234567
cd /home/tariq.qayyum/hpc/GapSlice-OJCS
.venv-contract/bin/python -m contractlab.hpc status --job "$JOB_ID" --sample 60
squeue -u tariq.qayyum
sacct -j "$JOB_ID" --format=JobID,JobName%24,State,ExitCode,Elapsed,TotalCPU,MaxRSS,AllocTRES%30
sstat -j "$JOB_ID.batch" --format=JobID,AveCPU,MaxRSS,MaxVMSize
seff "$JOB_ID"
tail -f "logs/gs_contract_research_${JOB_ID}.out"
tail -f "logs/gs_contract_research_${JOB_ID}.err"
```

For a pilot use `gs_contract_pilot` in the two log filenames. `sstat` may have no
running steps after completion; `sacct` remains authoritative. CPU/memory
accounting on this cluster has previously reported incorrect memory allocation;
retain per-task process RSS and final Slurm records when interpreting efficiency.

The status command reports committed experiments and fresh/reused worker totals
per stage. To inspect recent progress, completed workers and failed rank logs:

```bash
JOB_ID=1234567
cd /home/tariq.qayyum/hpc/GapSlice-OJCS
.venv-contract/bin/python - "$JOB_ID" <<'PY'
import json,sys
from pathlib import Path
project=Path.cwd()
job=sys.argv[1]
study=Path(json.loads((project/f'outputs/contracts/jobs/{job}.json').read_text())['study'])
print('Partial/final results:',study)
for stage in ['design','calibration','test','diagnostics','allocation']:
    workers=list((study/stage/'workers'/job).glob('*.json'))
    rows=[json.loads(p.read_text()) for p in workers]
    print(stage,'finished workers',sum(r.get('finished',False) for r in rows),
          'fresh',sum(r['fresh'] for r in rows),'reused',sum(r['reused'] for r in rows))
logs=project/'logs/contracts'/study.name/job
for path in sorted(logs.glob('*/progress-0000.log')):
    print(path)
    print('\n'.join(path.read_text().splitlines()[-3:]))
PY
grep -RniE 'error|fatal|failed|traceback|oom|killed|timeout' "logs/contracts/"
```

The grep may include old attempts; use the study/job directory printed above
to restrict it. Main replay ETA uses **fresh** completions, not validation of
reused records. Stage ETA is not a full-job promise; later stages and stragglers
add time. No fresh completions during startup/cache validation means no ETA yet.

## Results and downloads

The exact study path is stored in `outputs/contracts/jobs/<JOB_ID>.json`:

```
outputs/contracts/studies/contract-research-<fingerprint>/
  protocol.json, selected.json, contracts.json, tables.json
  <stage>/manifest.json, aggregate.json, complete.json, index.json
  <stage>/results/<task>.json and <task>.npz
  analysis/*.csv
  summary.json, report.html
  analysis_bundle.tar.gz, evidence_bundle.tar.gz, bundle_hashes.json
```

The analysis bundle includes all scientific manifests, design/calibration/test
aggregates, table certificates and complete allocation/PHY/SUMO/packet witnesses.
The evidence bundle contains the raw episode vectors and all scientific shard
commits, including negative results. It can be several GB. Both have SHA-256
hashes. Keep the full study directory as the primary archive.

After confirming the study suffix, download from the Mac:

```bash
rsync -az --progress \
  tariq.qayyum@10.90.24.15:/home/tariq.qayyum/hpc/GapSlice-OJCS/outputs/contracts/studies/contract-research-REPLACE_SUFFIX/analysis_bundle.tar.gz \
  /Users/rana/Documents/GapSlice-Trucks/v4_ojcs/hpc_results/contracts/
rsync -az --progress \
  tariq.qayyum@10.90.24.15:/home/tariq.qayyum/hpc/GapSlice-OJCS/outputs/contracts/studies/contract-research-REPLACE_SUFFIX/evidence_bundle.tar.gz \
  /Users/rana/Documents/GapSlice-Trucks/v4_ojcs/hpc_results/contracts/
```

## Recovery

First inspect `sacct`, main error logs and `outputs/contracts/jobs/<JOB>.status.json`.
After the failed job is confirmed terminal, preserve and archive only its guard:

```bash
cd /home/tariq.qayyum/hpc/GapSlice-OJCS
.venv-contract/bin/python -m contractlab.hpc recover --job FAILED_JOB_ID
.venv-contract/bin/python -m contractlab.hpc submit research --resume
```

For a failed pilot use `submit pilot --resume`. The helper checks the receipt,
Slurm user/project identity, terminal state, absence from the live queue and
exact recorded guard owner. It never cancels a job or removes another owner's
guard. Valid committed shards are hash-checked and reused, without resetting
seeds or overwriting complete results. Do not pull changed scientific code into
an active run: a changed source fingerprint creates a new study and cannot reuse
the old qualification as if it belonged to the revised method.

## What has and has not run

The repository verification note records actual local tests. The user's future
HPC pilot/research results are unverified until those jobs finish. All generated
episodes are synthetic. SUMO and LDPC are real executable software cross-checks,
not measured-data/testbed validation. Full NR Mode-1, field measurements, a
nonlinear string-stability theorem and journal acceptance remain unverified.
