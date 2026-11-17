# Local verification of the OJ-CS diagnostic branch

Verified on 17 November 2026. Inherited baseline: Git commit
`e9b883da49cfbaedcfc3e284bfbd31dfdccbce77`.

## Executed locally

- 21 selected tests passed: inherited model/channel/descriptor checks plus
  new feasibility, failure propagation and resume checks.
- All four synthetic diagnostic families completed in a real two-process local
  smoke run: four complete task records, zero failed and zero pending.
- Additional synthetic boundary checks completed for blocked/limited-bandwidth
  radio, perfectly correlated diffuse fading, 20-truck common-loss braking and
  320-tenant type-B market evaluation.
- Every new shell script and Batch passed `bash -n` individually. Python source
  passed compilation checks. Whitespace checks passed.
- The resume integration test deliberately fails a task, checks nonzero campaign
  status, executes the real radio task successfully, and verifies that a later
  invocation preserves the complete result without rerunning it.

The complete scientific suite command used was:

```bash
python -m pytest tests/test_revision_feasibility.py tests/test_revision_campaign.py \
  tests/test_model_consistency.py tests/test_channel.py \
  tests/test_descriptor_tables.py -q -p no:cacheprovider
```

The local smoke command was:

```bash
python -m gapslice.revision.campaign local --preset smoke --workers 2
```

The scientific library versions matched `requirements-hpc.txt`: NumPy 2.3.5,
SciPy 1.16.3, CVXPY 1.9.2, Clarabel 0.11.1, Matplotlib 3.11.1; pytest 8.4.2.
The local interpreter was Python 3.13.9. No new environment installation was
needed for those checks. Byte-identical regeneration of inherited PDF figures
and a full rerun of every original experiment were outside these checks.

## Not executed or established

- No Slurm job was submitted or run as part of this local verification.
- Cluster module versions, internet access for dependencies, memory availability,
  actual queue limits and multi-node shared filesystem behavior are unverified.
- The 2,004-configuration audit and 25,308-configuration full diagnostic campaigns
  have not been run by this verification.
- All new diagnostic inputs are synthetic. There is no measured-data/testbed
  validation, new control proof, new full-maneuver guarantee, full NR compliance
  claim, formal privacy guarantee or completed revised manuscript.

The inherited stored results were left unchanged. New local runtime outputs and
logs are excluded from Git; campaign manifests and task records are generated
inside each checkout when it runs. See [the research plan](OJCS_REVISION_PLAN.md)
and [the HPC runbook](HPC_OJCS.md) for the remaining work and cluster commands.
