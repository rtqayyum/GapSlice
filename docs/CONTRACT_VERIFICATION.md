# Contract framework verification — 2026-11-28

This record separates actual local execution from future HPC execution. It is
not a report of research superiority or a qualification of a physical system.

## Actually executed locally

- 18 new tests passed: statistical endpoint enclosure versus exact rational
  binomial probabilities; qualification floors and scope rejection; packing
  versus exhaustive enumeration; allocation witness rejection; baseline
  incumbent preservation; split independence/pairing; corrupt commit rejection;
  quota and 480-rank geometry; published equation checks; actual coded block
  roundtrips; actual SUMO IDM/ACC/CACC/custom controls; missing-AoI and physical
  completion regressions.
- 34 relevant existing tests passed using the existing scientific environment:
  `test_certified_method.py`, `test_certified_campaign.py`,
  `test_revision_feasibility.py`, `test_hpc_project_lock.py`.
- Python compilation and both new shell entrypoint syntax checks passed.
- Actual SUMO 1.28.0 executable and TraCI connections ran. Native CCC with the
  Table I safe gains kept its TH barrier positive; the unsafe gains produced a
  negative barrier; the native TH filter kept it positive. This was a declared
  braking scenario and equation-level check, not a digitized paper figure.
- All six transport/payload combinations (10/20/40 PRBs, 300/600 bytes) passed
  actual CRC/segmentation/LDPC/rate-matching/QAM/decoding noiseless roundtrips.
  A missing 64-QAM demodulator in py3gpp was caught; the explicit max-log adapter
  is exercised by those tests. Fitted and independent held-out noisy blocks
  were also executed by the complete smoke pipeline.
- The final complete smoke study executed 104/104 required tasks: PHY fit 2,
  PHY holdout 2, external SUMO 9, design 10, calibration 20, test 20,
  diagnostics 34, packet benchmarks 6, allocation 1. Both bundles were generated
  and inspected. The analysis bundle contains all 96 source/proof/launcher files;
  the evidence bundle contains 84 compressed physical episode shards plus all
  scientific commits. Archive hashes and raw-vector hash checks succeeded.
- Restart verification reused all 104 scientific task commits with zero new
  shards; the short native preflight checks still run as intended.
- The completed legacy scientific/execution fingerprint still exactly matches
  the archived pre-handover fingerprint. No old `gapslice` source, root `Batch`,
  old HPC shell script, old scientific test, requirements or proof was edited.

Verification commands:

```bash
.venv-contract/bin/python -m pytest tests/test_contract_core.py tests/test_contract_runtime.py tests/test_contract_external.py -q -p no:cacheprovider
.venv-contract/bin/python -m contractlab.hpc dependencies
.venv-contract/bin/python -m contractlab.hpc check --preset smoke
.venv-contract/bin/python -m contractlab.campaign run --preset smoke --local
```

## What the small executions mean

The smoke uses a 12-second horizon and tiny sample counts in its own namespace.
It qualified **zero** contracts; this is expected with four calibration episodes
and simultaneous confidence bounds. The empty allocation is a valid result,
not fabricated positive evidence. Nonempty solver/witness behavior is covered
by independently enumerated test problems.

A separate 128-episode, 40-second, five-truck no-radio hold check ran locally:
13.94 seconds walltime and about 230 MiB maximum process RSS on this Mac. It
observed 23 combined tracking/outcome failures, zero clearance failures and zero
physical-completion failures. This deliberately records a negative result: it
does not establish superiority, final qualification or an HPC runtime forecast.
The published/control alternatives and design choices must be assessed in the
fresh pilot/research protocol rather than tuned on these verification outcomes.

## Still unverified

The Linux wheel/runtime, Slurm resource allocation and full 480-rank uneven-exit
probe require actual HPC execution. The pilot/research studies have not been
submitted from this machine. The QoS/Slurm parsing and launcher constraints have
local checks, not a claim of remote execution. A pilot with the exact current
source/runtime is required before the research launcher will submit.

All generated trajectories/channels are synthetic. SUMO and LDPC are separate
software backends, not measured sensor/radio/road data. Full NR Mode-1, embedded
latency, external researcher replication, full-system nonlinear string stability,
novelty and Q1 journal readiness remain to be established. Read the method's
explicit native/adapted baseline matrix before interpreting any comparison.
