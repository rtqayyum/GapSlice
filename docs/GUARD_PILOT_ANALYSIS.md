# Reproduce the frozen analysis of Guard pilot 3098556

This workflow analyzes the first exploratory Guard pilot. It does not rerun
physical episodes or establish that the prototype is novel or superior to
published methods. The report narrative is explicitly pinned to campaign
`guard-pilot-3915091fe85a87dc`; do not reuse that prose for another study.

Keep the original archive unchanged. Extract it into a separate directory
after checking for absolute paths, parent traversal, links and special files.
The exported layout must retain `outputs/guard/`, its source-commit record,
manifest, task records, summary and selection report.

Run with the scientific requirements installed:

```bash
python scripts/analyze_guard_pilot.py \
  --export /ABSOLUTE/EXTRACTED_EXPORT \
  --campaign guard-pilot-3915091fe85a87dc \
  --repo /ABSOLUTE/ORIGINAL_SCIENTIFIC_CHECKOUT \
  --output /ABSOLUTE/SEPARATE_ANALYSIS_DIRECTORY
```

Outputs are a self-contained `report.html`, `analysis.json`, `cells.json` and
`guard_pilot_findings.png/.svg`. The raw export remains unchanged. Derived
outputs regenerate in the selected analysis directory. The HTML report
explains qualifications, abstentions, matched controller ablations, completion
time costs, scheduling limitations, calibration power and next research gates.

The reader checks the canonical manifest/task/profile identities, exact result
membership, all episode-vector lengths and the joint event against its tracking,
clearance and completion components. It checks packet denominators, CPU/RSS
accounting and worker completion. Fingerprinted source/input/execution files are
checked against the recorded Git snapshot. Scientific modules used to replay
qualification must match their recorded hashes; monitoring scripts can have
changed since execution. If the current scientific implementation has changed,
provide an original checkout with `--repo` rather than bypassing the checks.

Selection, qualification and admission are recomputed without using test outcomes
to fit selectors. Stored admission schedules, risk labels, utility/resource sums
and objectives are checked independently. Recomputed MILP ties can choose a
different allocation with the same objective. This is optimization replay of
existing evidence, not new physical validation.

Interpretation rules:

- A steady 1.5 s profile does not demonstrate a successful shorter-gap maneuver.
- The joint event includes tracking error and missed completion, so its rate is
  not a collision probability. Report those components separately.
- Identical seeds with different batch sizes do not preserve every plant draw
  in this simulator. Perfect-radio controls are not episode-paired with main
  tests; the governor ablations at identical batch sizes are paired.
- Per-cell absolute-risk intervals are pointwise exact binomial intervals.
  Paired differences use conservative exact bounds on the two discordance
  probabilities, avoiding zero-width t intervals at observed boundaries.
  These exploratory comparisons have no adjustment across the full analysis.
- Test-risk confidence bounds for the one qualified Guard action are adjusted
  across its two environments; qualification itself follows the separate,
  prespecified family-error allocation.
- A first-slot packing bound is specific to the offered synchronized templates,
  not a physical network-capacity theorem.
- Power curves assume alternative risks; they are sample-planning calculations,
  not new measurements or retroactive qualifications.
- This test set has now been inspected. Development may learn from it, but a
  redesigned method needs a new frozen protocol and fresh final evidence.

Seven additional local checks cover altered event/count/denominator evidence,
missing/nonfinite values, null rejection probability and nondegenerate paired
uncertainty. Raw archives and generated reports remain outside Git.
