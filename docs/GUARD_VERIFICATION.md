# Guard prototype verification, 18 November 2026

Executed locally on macOS ARM64 with Python 3.13.9 and the pinned scientific
requirements. The cluster commands below are prepared for execution by the
project owner; no new cluster job is claimed here.

- 63 selected checks passed together: 23 new Guard checks, eight offline audit
  analysis checks and the 32 previously selected runtime/model/diagnostic checks.
- The new checks cover binomial-test boundaries, fixed-sequence stopping,
  heterogeneous risk labels, environment qualification, discrete payload/TBS
  accounting, retained hopping geometry, slot/half-duplex constraints, exact
  small admission references, fleet risk-budget enforcement, independent random
  streams, equilibrium, failed maneuver completion, perfect/absent radio controls,
  test-set separation and real worker failure/recovery/resumption.
- A real two-process local smoke campaign completed 10/10 tasks and 80 episode
  replays, with no failed or pending tasks. Latest local campaign:
  `guard-smoke-2caa0a60da04c939`. Task CPU was 7.356 seconds; maximum cumulative
  process RSS was 57.031 MiB. These are local measurements, not HPC estimates.
- Every shell script and Batch passed `bash -n`. New Python source passed
  compilation checks, and Git whitespace checks passed.
- Isolated synthetic `scontrol`/`sbatch` capture checked smoke/pilot routing,
  four/40 CPU tasks, shortq maximum-runtime propagation, absolute Batch path,
  stage/preset exports and absence of GPU requests. It did not contact Slurm.
- A separate exploratory numerical check replayed 16 matched perfect-radio,
  noise-free-sensor episodes for each of two target gaps and governor on/off.
  Changing dt from 2 ms to 1 ms preserved all four cells' violation counts;
  maximum changes in per-episode peak tracking error were below 0.018 m.
  This small check includes packet-time quantization changes and is not a
  comprehensive convergence proof or independent physical validation.

The complete local check command was:

```bash
python -m pytest tests/test_guard_method.py tests/test_audit_analysis.py \
  tests/test_hpc_project_lock.py tests/test_hpc_python_runtime.py \
  tests/test_revision_feasibility.py tests/test_revision_campaign.py \
  tests/test_model_consistency.py tests/test_channel.py \
  tests/test_descriptor_tables.py -q -p no:cacheprovider
python -m gapslice.guard.campaign local --preset smoke --workers 2
```

Batch's Guard stage runs the 32 selected startup checks and the 23 Guard checks;
the eight offline analysis checks are additional local verification. No new
dependencies or shared-Conda writes were introduced. Outputs/caches remain
project-local, inherited inputs/results remain unchanged and raw local evidence
is excluded from Git.

Unverified: Linux/Slurm execution of this new module, its exploratory pilot,
multi-node operation, real PHY curves and signaling, measured/testbed data,
independent backend agreement, a reliable operating-domain classifier,
application-grounded tolerances, comprehensive grid convergence, continuous-time
safety or string-stability proofs, novelty beyond the identified prior art and
superiority over faithfully implemented published methods. Successful software
checks establish none of those scientific claims.

See [the method](GUARD_METHOD.md) and [the exact HPC commands](HPC_GUARD.md).
