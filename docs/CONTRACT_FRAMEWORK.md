# GapSlice contract framework: protocol v1

This is a new synthetic research study, not a relabeling of the completed
`cert-research-16130d0ca159e816` experiment. It deliberately makes no promise of
better results, a Q1 acceptance, novel control theory, or real-road safety.
The completed code, data, source fingerprint and Slurm entrypoint are preserved.
All new Python code is in `contractlab/`, outside the old scientific fingerprint.

## Research question and proposed contribution

Can a controller-agnostic compiler expose qualified outcome/resource contracts
and select among them under shared radio and fleet risk constraints, while
preserving valid baseline incumbents and reporting independently checked bounds?
The claim to investigate is the value of **selecting and composing contracts**,
not that the fused predictor universally beats hold or radar. Restricted-menu
dominance on the calibration objective follows from feasible-set inclusion; it
is a sanity check, not a novel theorem or independent evidence of superiority.
The novelty against the wider contract/admission/safety literature still needs
a systematic comparison before manuscript claims are finalized.

## Contract and proof scope

A contract records the controller and parameters, maneuver and payload, cyclic
radio schedule, 40-second horizon, sensor/lag/channel context, outcome event,
source/dependency hash, backup-table witness, risk confidence cost and lower
confidence value. Admission checks must also establish the actual operating
assumptions and initial backup feasibility; string labels are not sensors.
`deployment_allowed` is deliberately only a metadata check. This is a research
compiler, not a production admission service with hardware attestation.

The outcome event is the union of a sampled clearance below 2 m, a moving
reference spacing error above 5 m, invalid initial backup feasibility, or failure
to attain the **actual** target spacing `2 + h_target*v` within 1 m on every link
for a continuous 2-second dwell before the horizon. The primary reward is the
time-average realized headway reduction, clipped to `[0,1.5-h_target]`, and zeroed
on any outcome violation. Internal reference completion is no longer called
physical completion. Safety, tracking and attainment are exported separately.

The reused outward-rounded stopping-envelope shield and one-sided observer
argument retain exactly the conditional scope in
[CERTIFIED_PROOFS.md](CERTIFIED_PROOFS.md). They do not prove full nonlinear
string stability. Jerk/lag/sensor/initial-state assumptions must actually hold.
The sampled minimum in an experiment is not by itself an intersample proof.
The new code does not replace or weaken these assumptions to manufacture wins.

For each of the `M` frozen candidate/context cells with `k` violations in `n`
independent calibration episodes, invert the binomial CDF at `alpha/M`, with
`alpha=0.025`. Round its upper endpoint **up** onto the 1e-6 probability lattice.
A directed-rounding Decimal evaluation verifies
`P[Binomial(n,p_upper) <= k] <= 0.025/M`; an unverified numerical endpoint is never
accepted. The remainder of the 95% family confidence budget is 0.025 for bounded
reward Hoeffding lower bounds. Calibration data select qualification and value;
test data never change menus, risk costs, gains or policy parameters.

With family confidence at least 95%, every qualified risk/value inequality
simultaneously holds for this fixed declared distribution. For selected tenants,
the union bound gives `P(any outcome violation) <= sum(p_i) <= fleet_budget`.
It needs no independence between tenants. Additive expected value also needs
no tenant independence. Neither conclusion holds automatically under a changed
operating distribution, a different horizon or unmodeled measured channel.
Selection based on the calibration family is covered by simultaneous bounds.

This removes the old arbitrary 16-admission ceiling. A legitimate statistical
floor remains: a zero-failure upper bound is positive at finite `n`. Every report
retains that floor and sweeps 1%, 2% and 5% fleet budgets. The program must not
admit an unlimited number of tenants because no failure happened in a small run.

## Allocation witnesses and baselines

Each finite column chooses one qualified contract, absolute packet phase and
frequency offset for a tenant. Constraints enforce one choice/tenant, cyclic
PRB occupancy, half-duplex, deadlines, payload feasibility and summed risk cost.
The MILP returns an incumbent, not an assumed global optimum. A deterministic
feasible greedy solution is always available, and the union-menu solve retains
the best independently valid baseline incumbent. Every chosen schedule is
rechecked across three epochs using the independent slot validator.

An exact-rational Lagrangian upper bound drops radio conflicts and evaluates
`lambda*B + sum_i max(0,max_j(value_ij-lambda*risk_ij))`.
Each evaluated rational expression bounds the finite packing optimum; integer
ceiling preserves the bound. This is independent of the MILP optimality flag.
It is not a certificate for every possible continuous radio/control policy.

Methods include controller-restricted hold, radar, fused, IDM, CCC and CCC-CBF
menus; a no-radio menu; a static minimum-PRB engineering reference; greedy union;
and the exact union with incumbent retention. All see identical tenant mixes,
risk budgets, qualification criteria and radio capacity. Loads are 8/16/32/64/128,
capacities 51/106 PRBs and risk budgets 1/2/5%, with 30 predeclared workload seeds.
No-radio is a substantive comparator and is allowed to win.

Held-out allocation value is the sum of independent-test cell means. The reported
empirical marginal-risk union bound is not a measured joint-fleet failure rate.
Descriptive workload win counts are not independent statistical significance
tests. Shared-seed physical reward contrasts have explicit simultaneous bounded
difference intervals and include negative and inconclusive outcomes.

## Published baseline provenance

| Reference | Executed implementation | Scope and adaptation |
|---|---|---|
| Treiber, Hennecke & Helbing, PRE 62 (2000), [IDM](https://doi.org/10.1103/PhysRevE.62.1805) | IDM acceleration equation; separate SUMO-native IDM | Published law with standard zero additional-gap term; chosen truck parameters and common physical/backup limits in primary plant are adaptations. |
| Molnar, Orosz & Ames, CDC 2023, [CCC/CBF](https://arxiv.org/abs/2309.00074) | Native Eq.1–3 and time-headway filter with Table I gains, high-accuracy SciPy ODE check | Declared braking input, not digitized reproduction of a paper figure. Native safe/unsafe/filtered cases are checked separately. |
| Same CCC/CBF reference | Lagged, jerk-limited, changing-reference CCC and relative-degree-two TH-CBF adaptation | The moving-reference derivatives are included. Original paper's theorem is **not transferred**; the common backup shield is the primary plant's conditional safety mechanism. |
| Milanés/Shladover and Xiao et al., maintained [SUMO ACC](https://sumo.dlr.de/docs/Car-Following-Models/ACC.html) and [CACC](https://sumo.dlr.de/docs/Car-Following-Models/CACC.html) | Actual pinned SUMO 1.28.0 native ACC/CACC processes | Includes SUMO collision avoidance additions, explicitly preserved. Native CACC receives its ideal cooperative model; it is not silently subjected to a packet model SUMO does not implement. |
| Mandal, Roy & Palit, [eV2X resource allocation study](https://arxiv.org/abs/2411.01525) | Max-C/I, PF and DRR policy cores on a common abstract packet harness | Shared deadline/half-duplex veto is our adaptation. This is packet-level QoS evidence, **not** reproduction of their OMNeT++ architecture or an end-to-end controller baseline. The cited source is a preprint; established policy cores are not a new published whole-system reproduction. |

Hold and radar are strong internal ablations, not newly invented published
baselines. A homegrown controller is never labeled as an exact reproduction of
a published predictive safety filter, robust MPC, or full previous system.

## Independent software validation

1. **SUMO 1.28.0:** headless executable and TraCI, ballistic integration on a
   fixed single lane. Actual SUMO-native IDM/ACC/CACC and all six custom controls
   execute under the same initial speed/braking seed. Native controllers retain
   their documented safeguards; custom controls disable hidden speed clamping
   and apply explicit lag/jerk/backup behavior. Differences in these capabilities
   are reported. The primary proof does not transfer to this 10-ms SUMO
   ballistic integration (the primary exact-lag plant uses 2-ms integration).
   Nominal observer/control clocks are 10 ms in both; custom periodic packets
   use the same explicit 0/40/70-ms releases per 100-ms superframe.
   Custom perfect/bursty cooperative input checks are cross-model stress tests,
   not qualified coded-PHY SUMO contracts. Native CACC is an ideal-information
   comparator. No measured traffic trace is claimed.
2. **py3gpp 0.6.0:** actual CRC, segmentation, LDPC encoding, rate matching, QAM,
   AWGN, soft demodulation, rate recovery, LDPC decoding and CRC checks. The
   package lacks a working 64-QAM demodulator; our explicit max-log demapper is
   tested against the external modulator. All six configured transport blocks
   must roundtrip without noise before a study starts. Decoder: 12 normalized
   min-sum iterations. This remains a software-coded AWGN model, not full PSSCH.
3. Fit and held-out coded blocks use separate RNG namespaces. The primary replay
   uses a frozen nonincreasing upper-envelope step lookup; below the fitted SINR
   grid BLER is one, and above the grid it is not extrapolated to zero. Finite
   block uncertainty, fitted/held-out counts and disagreements are exported.
   Qualification is **conditional on this frozen stochastic lookup**. It does
   not certify the true physical BLER curve or include a full sidelink PHY.

The AWGN curves replace the previous uncalibrated finite-blocklength formula;
the fading, interference and bounded sensing distributions remain illustrative.
NR Mode-1 signaling/control channels, channel estimation, PSFCH/HARQ, a real
resource pool implementation, and measured radio traces remain absent.
py3gpp is a third-party dependency with its own AGPL license; SUMO and its data
packages also retain their upstream licenses. Their source is not copied here.

## Frozen experiment and auditability

Research cases: the Cartesian product of N=3/5, target=.9/1.2 s and 51/106 PRBs
at 300 bytes, plus two declared 600-byte cases. Two parameter choices/controller
are compared on 64 design episodes. A finite set of serial/parallel/hopped
profiles, 10/20/40 PRBs, one/two blind copies and phases 0/30 ms is considered.
For each controller/case, retain a design-selected no-radio option and, where
used, one design-selected radio option. Radar and IDM never buy unused radio.
Every selected option is independently qualified in nominal, blocked and
sensor-uncertain contexts. There are at most 300 selected context cells.

Each cell has 65,536 calibration and 65,536 held-out episodes, in 128-episode
resumable shards: at most 39,321,600 main episodes, plus design/diagnostics.
Episode batches and all policy/profile comparisons use reproducible component
streams. Pairing requires equal dimensions, context, split and batch shape;
different radio phases do not imply identical time-indexed fading realizations.
Speeds, lag endpoint/interior/alternating mixtures and braking pulse classes are
predeclared. Separate slow/hard and alternating/hard combinations, perfect-radio
and no-shield diagnostics are not allowed to retune contracts.

Smoke and pilot use **different namespaces** and lower counts. Smoke shortens
the horizon to 12 s. Neither is qualification evidence for the research study.
The pilot is an infrastructure/throughput gate, not positive-outcome selection.
Every policy and every negative/inconclusive cell remains in the exported data.

Each required shard writes compressed episode vectors, a SHA-256 checked commit,
task identity, CPU/wall/RSS data, and controller/plant assumptions. Scientific
writes fail closed. Optional worker telemetry has bounded retries and cannot
invalidate already committed scientific results. Completed work is validated
and reused on restart. A failed worker exits the stage before a huge cache scan.
All stage manifests, design/calibration/test aggregates, raw vectors, allocator
witnesses, per-instance solver timings, paired contrasts and report tables are
preserved. Maximum guard timing is for a **batch**, not per-vehicle embedded
latency. Empirical acceleration L2 gains diagnose amplification, not stability.

Packet age is finite only after actual delivery. No-radio maximum/mean AoI is
missing (`null` in JSON, NaN in raw NPZ); startup absence and longest outage are
separate. The old artificial 40-second age maximum is not reused.

## Remaining journal evidence

Completion of this program is not automatic journal readiness. Required next
evidence includes measured channel/sensor/actuator bounds with provenance; a
validated full packet/NR backend if making NR claims; independently qualified
SUMO/other-model contracts if making cross-model guarantees; a systematic recent
novelty comparison; an external researcher replication; and either a correct
full-system stability result or appropriately narrowed claims. If hold/no-radio
continues to win, that result must change the paper's story rather than be hidden.
