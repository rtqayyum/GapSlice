# Verification of the OJ-CS diagnostic branch

Verification began on 17 November 2026, with managed-runtime follow-up on
18 November 2026. Inherited baseline: Git commit
`e9b883da49cfbaedcfc3e284bfbd31dfdccbce77`.

## Executed locally

- 32 selected tests passed: inherited model/channel/descriptor checks plus
  new feasibility, failure propagation, resume, project-guard and runtime checks.
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
- Guard tests use real shell processes to check acquire/release, competing
  owners, preserved unknown/changed ownership, and filesystem error reporting.
  A controlled module-load failure exercises Batch twice and verifies that the
  real failure phase is recorded and neither startup strands a guard.
- Runtime tests create/reuse a real isolated venv, preserve incompatible inputs,
  reject an external venv symlink and unverified installer, and simulate an old
  module interpreter to verify managed-runtime selection and error propagation.
- In a separate actual download check, the official pinned uv installer and
  CPython 3.13.9 were installed inside a local validation project, and a seeded
  isolated venv was created successfully. The pinned scientific requirements
  were then installed into that clean environment, all 32 selected tests passed,
  and all four smoke configurations executed successfully with two workers.
  The same 32 tests also passed under the original Conda interpreter. These
  local checks ran on macOS ARM64, not on a Linux cluster.

The complete scientific suite command used was:

```bash
python -m pytest tests/test_hpc_project_lock.py tests/test_hpc_python_runtime.py \
  tests/test_revision_feasibility.py tests/test_revision_campaign.py \
  tests/test_model_consistency.py tests/test_channel.py \
  tests/test_descriptor_tables.py -q -p no:cacheprovider
```

The local smoke command was:

```bash
python -m gapslice.revision.campaign local --preset smoke --workers 2
```

The scientific library versions matched `requirements-hpc.txt`: NumPy 2.3.5,
SciPy 1.16.3, CVXPY 1.9.2, Clarabel 0.11.1, Matplotlib 3.11.1; pytest 8.4.2.
Both local distributions used Python 3.13.9. Byte-identical regeneration of inherited PDF figures
and a full rerun of every original experiment were outside these checks.

## Cluster execution supplied by the project owner

The owner submitted and ran these jobs. The analyst did not log into the
cluster. Supplied logs and the downloaded audit export establish the following
execution record; file/identity checks are internal consistency checks, not
independent authentication of Slurm accounting.

- Smoke job `3097319` completed with exit code 0 in 54 seconds: all 32 selected
  checks passed and all four diagnostic tasks completed using four workers.
  Campaign: `ojcs-smoke-7dde9f5a73400630`.
- Audit job `3097320` completed with exit code 0 in 193 seconds: all 32 selected
  checks passed and all 2,004 tasks completed using 40 workers. Campaign:
  `ojcs-audit-169cb7962b787c5e`. There were no failed or pending records.
- The worker step took 147 seconds. Results identify one compute host, `cn114`.
  Task process CPU summed to 2,783.706 seconds. The largest cumulative
  process RSS was 149.059 MiB; it is not aggregate job memory.
- Offline verification on 18 November 2026 checked the manifest digest, every
  task ID/configuration/status, exact result-file membership, family totals,
  summary CPU/RSS accounting and all 59 source/input hashes against the local
  checkout. Runtime and dependency details are preserved in the export.
- Completion is distinct from scientific availability: the audit contains
  36 radio and 144 control records reporting unavailable inherited descriptors.
  Detailed findings and raw exported results remain in the owner's local audit
  directory; no cluster-result archive is added to Git.

The previous guard/module/venv startup failures are historical. The managed
Python runtime resolves the base executable and uses symlinked venv binaries;
subsequent preparation, fixture checks and both successful jobs exercised it.
The original cluster filesystem failure underlying the old flock guard was
not diagnosed.

## Offline evidence analysis

`scripts/analyze_ojcs_audit.py` analyzes an exported audit without rerunning
scientific tasks or requiring the analyst's runtime to match the cluster.
It produces a self-contained HTML report, PNG/SVG figure, JSON analysis and
CSV tables with original result IDs. Raw inputs remain unchanged.
Eight additional local checks exercise source/identity/accounting drift,
missing/failed records, jointly feasible savings denominators, ACC-relative
utility ratios and seed-cluster treatment. These checks are separate from
the 32-check Slurm startup suite. All 40 checks passed together locally on
18 November 2026. The real exported audit generated the HTML/JSON/CSV outputs
and PNG/SVG figure; the figure was visually inspected and report artifact
links were checked. No new simulation tasks were run for this analysis.

See [the analysis workflow](OJCS_DIAGNOSTIC_ANALYSIS.md). The larger diagnostic
preset is not the next research gate: analyze the inherited-model failures,
revise the coupled model and freeze the final evaluation protocol first.

## Not executed or established

- Multi-node shared-filesystem execution remains unverified; all exported
  audit task records identify the same compute host.
- The 25,308-configuration full diagnostic campaign has not been executed.
- All new diagnostic inputs are synthetic. There is no measured-data/testbed
  validation, new control proof, new full-maneuver guarantee, full NR compliance
  claim, formal privacy guarantee or completed revised manuscript.

The inherited stored results were left unchanged. New local runtime outputs and
logs are excluded from Git; campaign manifests and task records are generated
inside each checkout when it runs. See [the research plan](OJCS_REVISION_PLAN.md)
and [the HPC runbook](HPC_OJCS.md) for the remaining work and cluster commands.
