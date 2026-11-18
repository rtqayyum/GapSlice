# Redesign verification — 2026-11-18

## HPC startup cleanup fix — after job3098812

The first real HPC smoke job3098812 passed the32 inherited checks and all17
new functional checks, then failed during TemporaryDirectory teardown with
ENOTEMPTY. The class fixture still owned three open memory-mapped proof arrays
when their directory was removed. This is consistent with shared/NFS filesystems
retaining open, unlinked files; a directory listing/filesystem trace was not
available to confirm the exact filesystem mechanism. The scientific campaign
had not started. Research job3098813 remained pending with
DependencyNeverSatisfied after that smoke failure.

The fix explicitly closes owned mappings before fixture cleanup. Shield now
supports idempotent close/context management and rejects use after closing;
verification, worker exit and path-owned simulator calls release mappings on
normal and exceptional exits. Table builders close their mappings after flush
and use context-managed hash input streams. No physical parameters, seeds,
equations or qualification thresholds changed. No cleanup exception is ignored
and no functional test is skipped. NumPy2.3 exposes no public memmap.close;
the pinned implementation's backing mmap.close is isolated in one helper,
with regression checks for the mapping lifetime
([NumPy documentation](https://numpy.org/doc/2.3/reference/generated/numpy.memmap.html)).

After the fix, **51/51 local launch checks passed**, including two additional
mapping-lifetime checks. The complete local smoke study
`cert-smoke-5164b7a4dcf8e06e` finished successfully. All24 raw-result shards and
their scientific summaries exactly matched the previously verified smoke
study, including every per-episode vector. Compilation, shell syntax and diff
checks passed. The shared-filesystem fix still requires the user's new HPC
smoke run; no successful HPC rerun or research execution is claimed yet.

The evidence below records the earlier local redesign verification, before
the two resource-lifetime regression tests were added.

## Executed locally

* **49/49 launch checks passed**: project lock/runtime, inherited feasibility,
  model/channel/descriptor checks, and17 new certificate/campaign checks.
* **89/89 tests excluding the legacy rendering fixture passed** (24.71 seconds).
  Python compilation, all Batch/HPC shell syntax checks and `git diff --check`
  passed. No old scientific module or stored result was changed.
* Real complete local synthetic smoke study:
  `cert-smoke-aac3e739e183c8a9`. Two design shards, four calibration, four test,
  four diagnostic and ten allocation tasks completed. There were112 physical
  episode replays in total;32 were held-out main episodes, with zero primary
  failures or safety/observer certificate breaches. Calibration n=16 correctly
  qualified **zero** contracts: a smoke run cannot establish a1% risk label.
* The identical command was rerun to check recovery. Committed raw shard
  modification times remained unchanged; completed simulations were reused.
* Slurm was **mocked**, not contacted, to check both preflights occur before
  submission, research depends on smoke success, requested CPUs/memory/time
  are passed correctly, no GPU is requested, and a preflight rejection submits
  nothing. These are script tests, not evidence about university account limits.
* The independent numerical verifier checks80-digit Decimal exponential
  enclosures, high-accuracy independent plant integration,256 adversarial
  braking replays and the explicit Lyapunov witness. The sampled minimum
  braking-envelope slack was approximately0.01096m. These checks support the
  conditional mathematical arguments; they are not a universal numerical proof.
* Exact binomial acceptance counts for n=32768 and worst-case68040 family tests
  were independently compared against floating binomial CDFs in smaller unit
  cases. The large-family integer critical counts were {1:2,2:13,4:41,8:105,16:243}
  for risk units/1600. Floating probabilities do not make acceptance decisions.

## Development evidence, separate from final qualification

A new-model N=5,h=0.6,blocked,64-episode development replay had four incomplete
maneuvers, zero tracking/clearance failures. A different N=7,h=1.0,blocked,
2048-episode development replay had zero primary failures. The latter took237s
and peaked near808MiB. These are different contracts/sample sizes, not a matched
improvement, a final test, or a uniform zero-risk claim. They use the development
namespace, which is separate from `cert-research-frozen-v1`.

## Existing rendering-fixture limitation

The unrestricted suite still fails `tests/test_reports.py` at the original
figure byte-comparison fixture. Stored figures identify Matplotlib3.11.2;
the installed runtime is3.11.1. For `fig_ceb.pdf`, content/object streams match
when CreationDate/Creator/Producer metadata and dependent cross-reference
byte offsets are normalized. The original test only strips CreationDate.
For the raster image, maximum channel difference was1/255, RMS0.00601/255,
with0.00361% of channels different, consistent with this renderer difference.
The strict original test and stored figures were preserved unchanged. New HPC
launch checks do not depend on reproducing these legacy figure bytes.

## Not executed or established

The new heavy research study has **not** run on the university cluster. No
new job ID, quota, filesystem speed, account CPU limit or completion-time
estimate has been verified there. The launcher will perform scheduler
preflights and print actual job IDs when the user runs it.

All episodes above use synthetic physics/sensing/channel inputs. No measured
NR traces, testbed, road measurements, independent external simulator or
faithful additional published baseline has been validated. Full-system
nonlinear string stability, unconditional road safety, settled novelty,
superiority and Q1 acceptance are not claimed. See CERTIFIED_PROOFS.md and
HPC_CERTIFIED.md for the implemented conditional scope and the next run.
