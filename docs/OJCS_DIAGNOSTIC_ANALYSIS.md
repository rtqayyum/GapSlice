# Analyze an exported OJ-CS audit

This stage inspects inherited-model diagnostics to decide what to redesign.
It does not rerun experiments, validate the final proposed method, or turn a
successful Slurm exit into a scientific guarantee.

## Inputs and invocation

Preserve the exported directory layout from `outputs/ojcs/`, including the
immutable manifest, all task records and `summary.json`. Keep the original
archive unchanged. The analysis script accepts an already extracted export;
inspect archives for absolute/parent paths and links before extraction.

From the repository root, using an environment with the scientific requirements:

```bash
python scripts/analyze_ojcs_audit.py \
  --manifest /ABSOLUTE/EXPORT/outputs/ojcs/manifests/CAMPAIGN_ID.json \
  --source-root /ABSOLUTE/ORIGINAL_CHECKOUT \
  --output /ABSOLUTE/SEPARATE_ANALYSIS_DIRECTORY \
  --cpus 40 --job-wall-s 193 --worker-wall-s 147
```

The elapsed-time and CPU arguments above describe audit job `3097320`; supply
actual accounting for a different execution or omit those optional arguments.
This report template expects the `audit` preset. It uses fixed illustrative
audit cells for its plots and labels them explicitly.

`--source-root` is optional, but supplying it compares every fingerprinted
source/input file with its recorded SHA-256. Use the checkout that generated
the experiment. Source drift is an error, even if the changed file would not
affect a particular family. The analyst's OS and installed packages can differ:
this program reads the export rather than using the campaign execution CLI.

## Validation and outputs

The reader checks the canonical manifest identity, unique task/configuration
hashes, exact result membership, complete statuses, matching configurations,
family totals and CPU/RSS summary accounting. The analysis records its own
implementation hash and a digest of the supplied result records. These checks
detect inconsistency; they cannot independently attest where code executed or
prove that the inherited scientific models are correct.

Outputs are `report.html` (including an embedded figure), `analysis.json`,
`records.csv`, `radio_strata.csv`, `fading_cells.csv`, `control_cells.csv`,
`market_instances.csv` and `audit_findings.png/.svg`. Analysis output must be
separate from the export. Repeating the command regenerates these derived
outputs; it never edits the raw records or their manifest.

## Statistical and scientific interpretation

- Descriptor-unavailable cases remain separate from capped-plan failures.
  Resource savings use only cases where both compared target plans exist;
  coverage is reported separately. These are parameter-grid descriptions,
  not a sampled probability of feasibility in deployment.
- A missing radio plan means no plan within the diagnostic's 1–4 one-slot
  copies. It is not a general physical infeasibility theorem. The radio family
  does not call the separate multi-link schedule checker.
- Fading/control intervals use independent seed clusters; seed reuse across
  parameter cells does not create additional independent clusters. A grid
  mean is computed within each seed before paired margin effects are formed.
  Four audit seeds give exploratory, pointwise t intervals with three degrees
  of freedom. Neither those intervals nor the original Monte Carlo intervals
  certify a rare-event reliability target or simultaneous coverage.
- Mean-square command-energy gain and the probability of peak spacing-error
  growth are distinct outcomes. Finite pulse tests do not certify an induced
  norm, and zero observed nonpositive distances does not establish safety.
  A worst observed cell is a post hoc exploratory selection.
- Allocation ratios against exact references use only solver-proven optima.
  Utility above ACC is the primary ratio. Total-utility ratios include an
  offset that can conceal lost incremental value. All comparisons still use
  inherited abstract resource costs and illustrative utility functions.
- Menu timings depend on worker cache history. Market/MILP timings exclude
  menu generation and are not end-to-end signaling latency. Peak process RSS
  is not aggregate job memory. Single-host success does not test multiple nodes.

The planned response to consequential diagnostic failures is model revision,
independent validation and a frozen final protocol. See
[the research plan](OJCS_REVISION_PLAN.md) and [verification record](OJCS_VALIDATION.md).
