# GapSlice research revision for IEEE OJ-CS

Status: research protocol and diagnostic infrastructure. A revised method,
new proofs, final experiments and a submission-ready manuscript are pending.
This plan makes no claim about journal acceptance or journal ranking.

Following analysis of the completed inherited-model audit, a separate
[GapSlice-Guard prototype](GUARD_METHOD.md) now implements a different
finite-horizon service-synthesis path. It uses qualified risk/resource profiles,
checked packet-copy geometry and a fleet risk budget. The prior-art matrix and
open novelty/validation obligations are explicit. Its
[HPC smoke/pilot workflow](HPC_GUARD.md) replaces expanding the old diagnostic
grid as the next implementation step; it does not complete the gates below.

## Research question and positioning

Can a network operator turn a fleet's declared control requirement into an
implementable radio reservation, and change that reservation while preserving
a precisely stated finite-platoon control contract under modeled uncertainty?

The proposed computing contribution is an interface between private controller
models and shared resource management, with explicit feasibility checks and
runtime reconfiguration. Truck platooning remains the application. Generality
beyond this application must be demonstrated before it is claimed.

Working title: **GapSlice: Verifiable Resource Contracts for Multi-Tenant
Networked Platoons**. "Verifiable" is an objective, not an achieved claim at
this stage. Keep the current title in the inherited baseline until the method
and evidence support a replacement.

The [official OJ-CS call](https://www.computer.org/digital-library/journals/oj/cfp-open-journal)
covers computing theory, design, practice and applications, specifies the IEEE
Open Journals template and a 12-page double-column limit. Treat that as the
working main-paper budget and reconfirm the instructions before submission.
Do not promise the historical review-time target stated on that page.

## Proposed core contributions

1. **A precise, checkable contract interface.** Specify the controller/model
   family, platoon length, output being bounded, initialization, sampling and
   latency conventions, packet-age/loss process, uncertainty envelope, outage
   treatment and the exact guarantee. Distinguish finite-platoon amplification,
   uniform string stability, event risk, availability and collision avoidance.
2. **A feasible resource planner.** Couple transmit-power limits, bandwidth,
   discrete transport blocks/MCS and overheads to slot/subchannel assignments,
   half-duplex operation, retransmission timing and interference. Verify every
   returned schedule with an independent checker. Do not compare savings using
   a baseline reservation that cannot be implemented under the shared rules.
3. **Guarded reconfiguration.** Account for the entire gap maneuver, including
   nonzero initial state, time-varying gap and outages. Include the derivative
   term introduced by a changing spacing policy. Refuse or defer a transition
   that cannot meet the chosen contract; an ACC command is not an instantaneous
   safety or stability proof at a short physical gap.

The market is a supporting mechanism unless it adds demonstrated value beyond
simple allocation under the same information constraints. Claims are about
avoiding direct disclosure; choice histories and descriptors may enable
inference. A formal privacy guarantee needs a separate mechanism and proof.
Loan mechanisms may be redesigned or removed if whole-transition compliance
cannot be supported. Additional AI/cryptography features are not prerequisites.

## Work packages and decision gates

| Package | Required work | Gate before dependent claims |
|---|---|---|
| W0 Provenance and novelty | Match the reviewed/current PDF to the actual LaTeX source; pin inherited code and raw inputs; refresh primary literature through submission | Every main claim has a traceable source, theorem or experiment; novelty is assessed against current work |
| W1 Reproduction and diagnostics | Re-solve descriptor entries; replay the control model; identify allocation and inference weaknesses | Scientific checks pass in the recorded environment; inherited evidence remains labeled |
| W2 Radio and scheduling | Explicit bandwidth/power policy, NR payload accounting, time scheduling, interference and reuse | Every admitted case has a checked schedule; infeasible targets are reported as infeasible |
| W3 Control contract | Derive sufficient conditions with specified loss/delay and uncertainty assumptions; conservatively re-certify selected table entries | No unproved extension from availability to trajectory stability or from fixed gaps to varying gaps |
| W4 Reconfiguration | Include the full maneuver, finite resource headroom, communication outages and fallback dynamics | All promised conditions hold over the complete maneuver in the modeled regime, or the maneuver is rejected |
| W5 Allocation and disclosure | Explicit acceptance/payment rule, utility calibration/sensitivity, menu resolution, finite termination, complexity, signaling and inference analysis | Claims match the information model; full-information references are labeled; empirical bounds are not presented as universal theorems |
| W6 Independent validation | Choose a simulator/backend that actually supports the required sidelink mode and feedback, or implement and validate the missing pieces explicitly | Model fidelity and unsupported features are stated; self-consistency is not called external validation |
| W7 Final campaign | Run the rebuilt system and all matched baselines, ablations and held-out scenarios | All methods face the same physical constraints and evaluation data; no tuning on test outcomes |
| W8 Writing and artifact | Rebuild figures/tables from raw outputs; archive configs, seeds, code and environment; prepare 12-page main paper and supplement | Every numerical claim regenerates; open obligations and negative results are represented accurately |

## Experiment program

The first four families are implemented **diagnostics of inherited abstractions**.
They are not the final experiments of the redesigned system.

| Family | Question | Factors and measurements | Status |
|---|---|---|---|
| D1 Radio feasibility | Do the old resource requirements survive explicit per-slot limits? | Gap, burst model, platoon length, actuator lag, blockage, payload, Rician K, bandwidth; feasible-target rate and PRB cost with power/noise bookkeeping | Implemented analytical diagnostic; FBL and independent-copy assumptions retained |
| D2 Retransmission correlation | How much diversity is lost under correlated copies? | Synthetic diffuse-fading correlation, K, gap, allocation, copies and seeds; loss estimates and Monte Carlo error | Implemented; synthetic Rician model, no measured calibration |
| D3 Control stress | How sensitive are old descriptors to common losses and model violations? | Gap, burst length, size, lag, cross-link latent correlation, delivery margin, braking pulse and seeds; energy gain, spacing growth, distances | Implemented constant-gap diagnostic; delays, saturation and changing-gap dynamics remain pending |
| D4 Market quality and cost | Are near-optimality and overhead conclusions robust? | Tenant count, capacity, contract type and seeds; total and ACC-relative utility, LP upper bound, exact reference when solved, rounds and timing | Implemented for inherited abstract resource pools and illustrative utilities |
| E1 PHY fidelity | Does predicted delivery match an independent NR error model? | MCS/TBS, payload, power, bandwidth, SINR and correlated attempts; BLER/prediction error and deadline misses | Pending W2/W6 |
| E2 Coupled schedulability | Does cell-level admission yield feasible packet schedules? | Load, release offsets, half-duplex conflicts, reuse and interference; admission, misses, resource use and runtime | Pending W2 |
| E3 Loss/delay structure | Does the full communication process satisfy the contract? | Matched mean delivery with different bursts, packet age, delay jitter, common outages and channel changes | Pending W3 |
| E4 Disturbances and heterogeneity | Does control behavior generalize to disturbances and vehicles excluded from design? | Steps, pulses, chirps, emergency braking, heterogeneous lag/gains, sensing noise and actuator limits; all-follower trajectories and worst intermediate growth | Pending W3/W6 |
| E5 Full reconfiguration | Can a loan or gap change preserve the declared condition throughout? | Surge size, duration, repeated events, channel evolution and transition speed; full-maneuver violations, temporary headroom, served demand and recovery | Pending W4 |
| E6 Component ablation | Which components cause the observed benefit? | Fixed SLA; descriptor; feasible scheduler; uncertainty treatment; monitor; transition guard; market; guarded loans | Pending W2-W5; identical feasible scenarios |
| E7 Disclosure and algorithms | What do repeated choices reveal and what does the mechanism cost? | Menu resolution, price query count, utility families, prior knowledge and repeated rounds; inference accuracy/interval width, communication and computation | Pending W5 |
| E8 Scale and external scenarios | Does the implementation remain useful beyond the design distribution? | Multi-cell/handover if implemented, large populations, route/channel holdouts and independent backend; utility, compliance, overhead and scaling | Pending; do not claim unsupported multi-cell generality |

### Diagnostic presets

| Preset | Radio | Fading | Control | Market | Total configurations |
|---|---:|---:|---:|---:|---:|
| smoke | 1 | 1 | 1 | 1 | 4 |
| audit | 324 | 288 | 1296 | 96 | 2004 |
| full | 3888 | 2160 | 18000 | 1260 | 25308 |

"Configuration" is one executable task, not one independent control event.
The audit uses 200 brakes per supported control configuration and 20,000
fading realizations per fading configuration. Full uses 1,000 and 100,000,
respectively. Some gap/burst combinations lack inherited certificates; those
return an explicit unsupported outcome. Do not hide them as runtime failures.
These are initial exploratory budgets. Repeated seeds are separate task records;
final sample sizes require a precision calculation using independent clusters.

## Statistical and comparison rules

- Separate design, tuning and evaluation scenarios. If measured data become
  available, hold out complete routes/sessions/vehicles rather than adjacent
  packets, which may be strongly correlated. Current data are simulated only.
- Use paired scenarios/seeds where a comparison permits it. Aggregate uncertainty
  over independent populations or channel sessions, not millions of correlated
  packet samples. Report distributions and adverse cases as well as means.
- State confidence scope. Pointwise binomial or Monte Carlo intervals do not
  automatically cover a selected descriptor table or every configuration.
  Validate selected operating points on fresh runs or use simultaneous bounds.
- Choose final repetitions from a declared precision goal and pilot variability.
  For independent zero-failure trials, the one-sided 95% exact binomial upper
  bound is 1 - 0.05^(1/n); correlated trials need a different sampling analysis.
- Use the same power, bandwidth, timing, feedback, information and training
  budgets for comparisons. Show resource savings only on jointly feasible
  outcomes, with admission and infeasible-target rates reported separately.
- Call published-method adaptations adaptations. A hand-designed request rule
  is not a trained RL baseline. Train/reproduce a relevant method faithfully or
  present it as a clearly named surrogate. Include strong simple references.
- Report actual MILP termination/gap. The diagnostic LP relaxation supplies an
  instance upper bound, not a proof of the market's general approximation ratio.
  Report utility gains over ACC as well as total utility to expose baseline effects.
- Keep raw per-configuration records, negative outcomes, timeouts and failed jobs.
  Reassess hypotheses after diagnostics, then freeze the final evaluation protocol
  before using final test results. Do not tune toward a desired savings percentage.

## Validation and resources

The public repository currently contains simulation code and generated results,
not measured/testbed traces. HPC adds scale, not physical fidelity. The
[5G-LENA feature list](https://5g-lena.cttc.es/features/) currently describes a
Mode-2 sidelink extension and lists HARQ feedback as unsupported. It cannot be
treated as a ready-made validation of the required Mode-1/feedback mechanism.
Backend selection and any missing implementation remain W6 work.

Use CPU workers. The current simulator, numerical integrations and optimization
do not need CUDA. One Slurm task owns one independent configuration at a time;
workers share an immutable manifest and combine results at completion. They
do not accelerate a single non-parallel SDP by allocating more idle CPUs.

Initial compute workflow: smoke -> audit -> inspect failure/feasibility/runtime
reports -> model redesign -> final protocol -> final HPC campaign. The full
diagnostic preset is available for justified follow-up; it is not a substitute
for the model redesign and should not be launched merely to increase volume.

## Main-paper budget and completion standard

Provisional 12-page budget: introduction 0.75; related work 0.5; model 1.25;
method 2; analysis 1; implementation 0.75; evaluation 4.25; limitations/conclusion
0.25; references 1.25. Use the required template without shrinking fonts to
force a fit. Put long proofs, secondary grids and implementation detail in a
self-contained supplement; keep essential assumptions and principal evidence
in the main paper.

Completion requires a defensible contribution, correct claims, implementable
allocations, appropriate theoretical support, independent validation, matched
comparisons and reproducible evidence. A larger experiment count alone does
not meet that standard. No manuscript claim should be updated from these
exploratory diagnostics without checking the complete revised system.
