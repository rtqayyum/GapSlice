# Guard prototype verification, 18 November 2026

The local checks below ran on macOS ARM64 with Python 3.13.9 and the pinned
scientific requirements. Later cluster logs supplied by the project owner
are recorded separately below; the analyst did not log into the HPC.

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

## Subsequently supplied cluster logs

- Smoke job `3098512`, campaign `guard-smoke-c61d9db8317043f5`, completed with
  Slurm exit `0:0` in 57 s. All 55 selected startup checks and 10 tasks passed.
- Pilot job `3098556`, campaign `guard-pilot-3915091fe85a87dc`, reports application
  exit 0, 55 passed startup checks, 2,040/2,040 completed tasks, 40 completed
  workers and zero failed/pending tasks. Recorded task CPU is 13,960.422 s;
  the largest cumulative worker-process RSS is 72.754 MiB. Final Slurm accounting
  and the raw export have not yet been inspected for this pilot.
- A live `squeue` lookup for the pilot returned `Invalid job id`, causing the
  old `set -e` monitor to stop before accounting/stored-result inspection. The
  monitor now continues after queue/accounting lookup failures. Two isolated
  shell-command capture checks exercised an invalid queue ID with accounting
  both available and unavailable, and confirmed stored-result/progress output.

These supplied logs establish execution progress, not comparative scientific
performance or independent authentication. Export and analyze the frozen pilot
before updating its HPC checkout; the manifest fingerprints execution scripts
as well as scientific source.

## Export verification and offline analysis

The downloaded pilot export was subsequently inspected locally. All 2,040 task
identities and episode-vector accounting checks passed, covering 791,808 replays.
All 76 fingerprinted source/input/execution hashes matched Git snapshot
`792a97590bf6d6666efb38287317d1d9be4eedea`. Selection/qualification were replayed,
and all 20 stored method/domain/allocator schedules and risk sums passed the
offline checks. Every task identified the single compute host `cn002`.

The analyzer produces a self-contained HTML report, JSON aggregates and a
PNG/SVG figure; source IDs trace back to raw results. Seven dedicated local
integrity/statistics checks passed. The figure was visually inspected and all
report artifact links were checked. Raw exports and generated reports remain
outside Git. The report records both useful component results and limitations;
it does not claim broad superiority or a completed journal contribution.
See [the frozen analysis workflow](GUARD_PILOT_ANALYSIS.md).

Unverified: final Slurm walltime, aggregate job memory, multi-node operation, real PHY curves and signaling, measured/testbed data,
independent backend agreement, a reliable operating-domain classifier,
application-grounded tolerances, comprehensive grid convergence, continuous-time
safety or string-stability proofs, novelty beyond the identified prior art and
superiority over faithfully implemented published methods. Successful software
checks establish none of those scientific claims.

See [the method](GUARD_METHOD.md) and [the exact HPC commands](HPC_GUARD.md).
