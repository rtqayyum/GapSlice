# GapSlice-Guard: research prototype and falsifiable contribution

Status: a new implementation and exploratory protocol, not an established novel
result or submission-ready paper. The working contribution is **compiling a
finite-horizon outcome request into a frontier of executable reservations and
qualified risk labels, then allocating those reservations under both slot and
fleet-risk constraints**. This replaces the inherited scalar descriptor ->
unbounded PRB pool -> gap-market path. The market and stability loans are not
the central mechanism of this prototype.

Working title: *Trajectory-Calibrated Wireless Service Contracts for Networked
Platoons*. Retain the original manuscript separately until this approach earns
its claims. No journal quartile or acceptance outcome is promised.

## Novelty boundary and closest work

The following are established ideas, not our inventions. The search was updated
on 18 November 2026; this is a focused starting matrix, not an exhaustive review.

| Primary source | Existing contribution relevant here | Consequence for this project |
|---|---|---|
| [Ge et al., IEEE/CAA JAS 2022](https://www.ieee-jas.com/en/article/doi/10.1109/JAS.2021.1004060) | Bandwidth-aware event-triggered communication and platoon-control co-design | Generic control-aware scheduling is insufficient novelty |
| [Saoud, Girard and Fribourg, HSCC 2018](https://lsv.ens-paris-saclay.fr/Publis/PAPERS/PDF/SGF-hscc18.pdf) | Assume-guarantee/symbolic contracts for platooning | A contract interface alone is insufficient novelty |
| [Distributed reference-governor CACC, IEEE T-ITS 2018](https://ieeexplore.ieee.org/document/8013751/) | Constraint handling for CACC, with a high-fidelity model and hardware-in-the-loop evaluation | A reference governor is neither new nor evidence of comparable validation here |
| [Tian et al., CCTA 2020](https://thomasrantian.github.io/pdfs/Tian_CCTA_20.pdf) | Controller-mode/reference-governor management of platooning constraints and failures | Do not claim first probabilistic constraint handling or first governed platoon transition |
| [Angelopoulos et al., Learn then Test](https://arxiv.org/abs/2110.01052) | Risk qualification through multiple hypothesis testing | Exact-binomial/fixed-sequence qualification is borrowed statistical machinery |
| [Farzaneh et al., Quantile LTT 2024](https://arxiv.org/abs/2407.17358) | Quantile-oriented calibration, including a radio-scheduling example | Adding calibration to scheduling alone is insufficient novelty |
| [Xu and Lu, StreamLTT 2026](https://arxiv.org/abs/2611.04062) | Risk qualification for dependent deployment streams | Our iid episode result does not cover their setting or improve on it by assumption |
| [Lemmon et al., burst-dropout stability](https://www3.nd.edu/~lemmon/publications/2011/burst-paper-acm1.pdf) | Relating network service/burst properties to stability | Do not claim the first communication-service/control guarantee connection |

The hypothesis to investigate is whether the **risk/resource frontier tied to
actual copy geometry and complete governed maneuvers** gives an implementable,
useful multi-tenant allocation that scalar delivery targets and uncoupled
qualification cannot provide at comparable resources. The components above
already exist individually. A credible paper needs a clear algorithmic or
systems advance in their coupling, appropriate analysis and independent evidence.
If the full review finds the same coupling already developed, redesign it or
reframe the contribution rather than conceal the overlap.

## Explicit outcome and operating population

One observation is a complete 40 s maneuver episode. The prototype declares a
violation if **any** vehicle has a bumper clearance below 2 m, absolute spacing
tracking error above 5 m, or fails to reach the requested headway within 0.01 s
by the end of the episode. These are illustrative application tolerances, not
standardized safety values. They must be justified with domain evidence before
the final protocol. Outcomes are evaluated on the 2 ms simulation grid;
continuous-time intersample protection is not yet established.

The initial headway is 1.5 s. Candidate target headways are 0.6, 1.0 and 1.5 s.
The initial-state, braking, actuator and sensing distributions are recorded in
`Model` and the immutable task manifest. Qualification is a population risk over
those initial states and disturbances; it is not a guarantee for every state
inside an informal envelope. An online state-conditioned request needs its own
valid conditioning rule and evidence.

Declared domains are `los` (both nominal and strongly correlated finite channel
populations) and `blocked` (a separate adverse population). Qualification must
pass in every population within its declared domain. The domain is an external
input in this prototype. A reliable classifier and its misclassification budget
are not implemented. No guarantee extends to arbitrary interpolation between
the finite channel populations, unknown contexts or distribution shift.

## Profile generation and physical replay

A profile contains platoon size, initial/target gap, nominal transition time,
governor policy, payload, PRBs per copy, copy count, copy timing/frequency pattern,
radio deadline and bandwidth cap. Candidate patterns are clustered, time-spread
and time/frequency-hopped. Link identity is retained even when two patterns
occupy the same resource cells: their fading dependence can differ.

- Within a slot, links use disjoint PRBs. Adjacent platoon links cannot share
  a radio in the same slot. The prototype uses a common 10-PRB subchannel grid
  for widths and offsets. The global allocator credits no in-cell spatial reuse.
- Radio transmissions finish within 9 ms, leaving 1 ms modeled processing.
  Every profile and returned global schedule passes the separate slot checker.
- Discrete selected MCS values and TBS arithmetic follow a pinned Release-16
  specification. The configuration deducts AGC/gap symbols, DMRS and explicit
  PSCCH/SCI2 occupancy. These fields are configuration assumptions, not full
  channel implementations. Source: [ETSI TS 138 214 V16.14.0, clauses 8.1.3
  and 5.1.3.2](https://www.etsi.org/deliver/etsi_ts/138200_138299/138214/16.14.00_60/ts_138214v161400p.pdf).
- Decoding still uses an **uncalibrated normal-approximation surrogate**, not
  NR LDPC link curves. No feedback HARQ or combining gain is credited. SCI
  decoding/control signaling and grant delays remain separate validation work.
- Each transmitter uses fixed total power. Occupied bandwidth changes thermal
  noise. Two modeled external interferers supply a declared interference level;
  disjoint in-cell allocations do not add unmodeled co-channel transmissions.
- Synthetic complex fading has repeat time/frequency covariance, packet-to-packet
  persistence and a shared cross-link component. Slow shadowing is shared within
  an episode. Correlated packets/links are not counted as iid observations.
- Messages contain the predecessor command at generation, not a future/current
  value substituted at reception. Scheduled arrival includes processing and is
  rounded up to the integration grid. The 30 Hz release clock is likewise
  rounded up; this quantization is explicit.
- Physical-coordinate dynamics include heterogeneous actuator lag, command and
  jerk limits, noisy local range/relative-speed observations, stale packets and
  full gap changes. The spacing derivative includes `-h_dot * v`.

The local reference governor gates progress using tracking error, relative
speed, own acceleration/speed, the received predecessor command and packet age.
It is a heuristic candidate policy, not an invariant-set safety filter. It can
fail and must be evaluated. Pausing permanently fails the completion condition.
The same governed controller is used by all radio-selection baselines; the
matched no-governor ablation isolates the governor. This avoids attributing a
controller change to a better radio algorithm.

## Qualification, risk labels and allocation

1. Generate a finite profile bank and freeze its geometry/model/data namespace.
2. Use **design episodes** to order `(profile, risk label)` hypotheses. Labels
   are 0.25%, 0.5% and 1% episode risk. Rank by anticipated calibration power
   computed from design loss and predetermined calibration sample size; break
   ties without looking at calibration/test failures.
3. Use independent **calibration episodes** to test that ordered bank. For each
   environment, use the exact lower-tail binomial p-value at the proposed risk
   label. Take the maximum p-value across environments in the declared domain.
4. Fixed-sequence testing stops at the first failed hypothesis. Accepted labels
   form a qualified resource/risk frontier. Allocate the global 5% family error
   across domains and requested-headway chains. Multiple risk labels are already
   hypotheses within each chain, not unsupported interpretations of a pointwise
   confidence interval as a simultaneous confidence band.
5. Translate qualified templates in frequency without changing their internal
   copy geometry, and allocate at most one per tenant. Enforce resource-cell
   exclusivity and a **1% sum of qualified episode-risk labels across admitted
   tenants**. A fixed frequency translation requires a stationary channel law
   and the same external-interference population as qualification.
6. A transparent greedy rule is the scalable prototype allocator; a sparse
   binary MILP is the small-instance full-information reference. Neither is
   claimed as a new solver. Returned allocations are checked independently.
7. Evaluate frozen selectors on independent **test episodes**. Preserve
   abstentions, failed maneuvers and source IDs. Never choose parameters on test
   results and describe the reused test set as fresh confirmation.

Only `guard` and `bonferroni` use qualified risk labels. The heuristic baselines
use design risk estimates for planning and have no statistical risk guarantee.
This distinction is recorded in their admission results; identical nominal
budgets do not turn their estimates into bounds. All methods face the same
profile bank, physical model, uncertainty populations and slot constraints.
An allocation under a different information model must be labeled accordingly.

## Supported statistical argument (existing tools, applied here)

Fix a declared domain and candidate policy `p`, including its entire governor.
Let `R[p,e]` be the probability of the joint episode violation in population `e`.
For `n` iid calibration episodes and `k` violations, use
`pval[p,e,r] = BinomialCDF(k; n, r)` to test the null `R[p,e] > r`.
Under that null this p-value is super-uniform. If the profile violates its
target in any environment, `max_e pval[p,e,r]` is also a valid p-value for that
union null: acceptance requires rejecting the bad environment's null as well.
No independence between environment/profile test statistics is needed.

Conditional on independent design data, the hypothesis order is fixed. If any
bad label is accepted by fixed-sequence testing, the first true null in the
order must have been rejected. Its probability is at most the chain's alpha.
A union bound across declared chains gives family error at most the allocated
global alpha. This remains valid when profiles have different predeclared risk
labels. Arbitrary selection/packing among qualified labels preserves the event
that every selected label is valid.

On that event, the probability that any admitted platoon violates its complete
episode contract is at most the sum of its allocated labels. Independence across
platoons is unnecessary for this final union bound. This is a finite-population,
finite-horizon statement conditional on the declared distributions and correct
domain selection. It does not establish string stability, collision avoidance
for all trajectories, recursive feasibility, repeated-request lifetime risk or
validity under adaptive deployment/shift. The statistical bound is not a new
theorem beyond the cited testing machinery and elementary composition.

The named selector is fixed before test evaluation. Guard and Bonferroni are
separate comparison procedures, each with its stated family-error budget; the
analysis does not claim a joint 95% event across arbitrary post hoc switching
between both procedures.

## Falsifiable hypotheses and required comparisons

| Hypothesis | Test | Failure condition |
|---|---|---|
| Average delivery hides consequential temporal dependence | Match mean delivery/resource and vary persistence/copy geometry | No meaningful control-risk difference after matching |
| Direct outcome qualification avoids invalid admission | Guard vs delivery proxy and empirical outcome selection, evaluated on independent episodes | Similar/larger violation risk without an offsetting documented trade-off |
| A useful qualified risk/resource frontier exists | Plot bandwidth-time cost, qualified risk and admitted utility | Empty frontier or all useful profiles dominated |
| Coupled packing is useful | Risk-aware pattern packing vs scalar-resource planning; exact small oracle and runtime | Little allocation value or excessive cost after preprocessing |
| Reconfiguration must be included | Same radio profile with/without governor, including completion deadline | Benefit disappears with matched dynamics or is bought by never finishing |
| Results survive model fidelity changes | Time-grid study, realistic link curves, published control baselines, independent backend and measured evidence | Conclusions reverse or cannot be reproduced |

The delivery proxy is explicitly a heuristic, not an implementation of a named
published paper. The baseline set here is for prototype falsification. Final
evaluation must add faithful implementations of the closest applicable published
methods, with the same constraints and appropriate tuning budgets. Performance
against these internal baselines alone is insufficient for a strong journal claim.

## Execution and next gate

Smoke exercises the pipeline and deliberately has too few episodes to qualify
a 1% risk target. The pilot uses 42 governed profiles (three target gaps), three
channel populations and four seed batches. Per profile/environment it uses
128 design, 2,048 calibration and 2,048 test episodes. Matched no-governor tests
and perfect-radio controls are included. See [the runbook](HPC_GUARD.md).

The pilot is exploratory: further development may use its findings. The final
evaluation requires a new frozen protocol and a fresh data namespace, plus
validated PHY/vehicle behavior, an independent backend, application-grounded
thresholds, context-selection handling, stronger baselines, numerical convergence,
signaling costs and a complete claim/proof/evidence table. A larger synthetic
grid or a new name does not settle those obligations.
