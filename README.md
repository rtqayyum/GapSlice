# GapSlice

Reference implementation, results and figures of the paper

> T. Qayyum, A. Lakas, A. Al Warafy, B. Brik, and M. A. Ferrag,
> **"GapSlice: Task-Oriented 6G Network Slicing for String-Stable Truck Platooning,"**
> submitted to the *IEEE Open Journal of Vehicular Technology*.

In GapSlice, a truck platoon buys from the mobile network a **time gap at
which it stays string stable**, instead of a latency and reliability number.

1. Each fleet computes a **control descriptor**: the lowest message delivery
   probability at which its platoon meets the target at each gap and level of
   burstiness. It reveals neither the controller nor the vehicle data.
2. The operator turns the descriptor into the **control-effective bandwidth
   (CEB)**: the PRBs that each gap needs, planned per slow channel state so
   that all links of a platoon meet their targets together for a stated share
   of the time.
3. A **price-only gap market** (Algorithm 1) sets the gaps through posted
   prices, and **stability loans** (Algorithm 2) let platoons lend PRBs to a
   priority surge while they widen their gaps, within a clause written into
   the contract.

The contract is a string-stability target, not a collision-avoidance
guarantee. Safety measures (per-event spacing-error growth, smallest bumper
distance) are reported separately.

## Repository layout

```
gapslice/                 Python package (see docs/ARCHITECTURE.md)
  control/                CACC platoon as a Markov jump linear system, SDP certificate
  channel/                finite-blocklength link model, time-correlated channel
  descriptor/             type-A and type-B descriptor tables (build and look up)
  allocation/             CEB and water-filling, gap market (Alg. 1), loans (Alg. 2)
  scenario/               tenant population, gap menus and utilities
  simulation/             platoon simulators in physical units, end-to-end simulation
  evaluation/             contract and availability checks
  baselines/              adapted Yan-Haerri, Zhang and Lu methods
  experiments/            E1-E9, feasibility and sensitivity studies
  reporting/              figures and LaTeX tables from the stored results
results/                  stored result files used in the paper (+ run logs)
figures/                  figures of the paper and the supplementary material
tables/                   LaTeX tables of the paper and the supplementary material
tests/                    automated checks (pytest)
scripts/run_all.sh        full reproduction from scratch
docs/ARCHITECTURE.md      module map and paper-to-code table
```

## Installation

Python 3.11 or newer (the stored results were produced with Python 3.13).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

The semidefinite programs use CVXPY with the Clarabel solver. The optimum of
P1 uses the HiGHS solver shipped with SciPy.

## Quick start

```bash
make test                          # all checks, about 30 s
python -m gapslice list            # list the experiments
python -m gapslice figures         # redraw every figure from results/
python -m gapslice tables          # rewrite every LaTeX table from results/
python -m gapslice run e7 A        # run one experiment (contract type A or B)
```

`make test` checks that the jump-system model matches an independent
simulator of the trucks in physical units, that the two platoon simulators
agree run by run, that the channel model matches long simulated traces, that
entries of both descriptor tables re-solve to the stored values, that the
stored tables give the numbers quoted in the paper, and that the figures and
tables redrawn from `results/` are identical to the stored ones.

## Reproducing everything

```bash
bash scripts/run_all.sh                          # about 3.5 hours on 2 cores
```

This overwrites `results/`, `figures/` and `tables/`. To keep the stored
files and write the new ones elsewhere:

```bash
GAPSLICE_OUTPUT=$PWD/rerun bash scripts/run_all.sh    # or: make verify
```

All random seeds are fixed. With the pinned versions of `requirements.txt`,
we re-ran every experiment (feasibility, E1-E9, sensitivity) with this code,
and all 17 result files were identical to the stored ones. Entries of the two
descriptor tables re-solve to the stored values (type B exactly, type A
within the tolerance of the SDP solver, about 1e-7). Other solver or library
versions may change the last digits of some results.

| Step | Command | Output | Time* |
|---|---|---|---|
| Type-B descriptor table | `python -m gapslice run type-b-table` | `tail_table.npz` | 85 min |
| Type-A descriptor table | `python -m gapslice run type-a-table` | `gain_curves.npz` | 12 min |
| Feasibility, descriptors, PRBs per link | `python -m gapslice run feasibility` | `feas.json` | < 1 min |
| E1: certificate vs. Monte Carlo, per-event risk | `python -m gapslice run e1` | `e1.json` | 4 min |
| E2: string water-filling | `python -m gapslice run e2` | `e2.json` | < 1 min |
| E3: gap market | `python -m gapslice run e3 A` (and `B`) | `e3_A.json`, `e3_B.json` | 5 + 1 min |
| E4: priority surges and stability loans | `python -m gapslice run e4 A` (and `B`) | `e4_A.json`, `e4_B.json` | 7 + 6 min |
| E5: time-correlated channel, planning rules | `python -m gapslice run e5` | `e5.json` | 16 min |
| E5b: smallest reservation for the joint certificate | `python -m gapslice run e5b` | `e5_joint.json` | 8 min |
| E6: wrong burst length, online check, probation | `python -m gapslice run e6` | `e6.json` | 2 min |
| E7: end-to-end validation | `python -m gapslice run e7 A` (and `B`) | `e7_A.json`, `e7_B.json` | 5 + 2 min |
| E8: comparison with published methods | `python -m gapslice run e8 A` (and `B`) | `e8_A.json`, `e8_B.json` | 18 + 13 min |
| E9: correlated slow states across links | `python -m gapslice run e9 A` (and `B`) | `e9_A.json`, `e9_B.json` | 3 + 2 min |
| Sensitivity | `python -m gapslice run sensitivity` | `sens.json` | 6 min |
| Figures and tables | `python -m gapslice figures`, `python -m gapslice tables` | `figures/`, `tables/` | 15 s |

\*Wall-clock time on a 2-core machine. The two table builders use both cores
and must finish before the experiments that read their output.

## Paper item to code and data

Main paper:

| Paper item | Produced by | Data |
|---|---|---|
| Overview and architecture figures | drawn in the LaTeX source (TikZ) | -- |
| Descriptors and PRBs per link (Section IV-B) | `reporting.figures.fig_desc_ceb` | `gain_curves.npz`, `tail_table.npz`, `feas.json` |
| Time-correlated channel (Section IV-C) | `reporting.figures.fig_channel` | `e5.json` |
| Price-only gap market (Section IV-D) | `reporting.figures.fig_market` | `e3_A.json`, `e3_B.json` |
| Priority surges and loans (Section IV-E) | `reporting.figures.fig_surge` | `e4_A.json`, `e4_B.json` |
| Comparison with published methods, figure and table (Section IV-F) | `reporting.figures.fig_compare_main`, `reporting.tables.tab_compare` | `e8_A.json`, `e8_B.json`, `e4_A.json`, `e4_B.json` |
| End-to-end validation table (Section IV-G) | `reporting.tables.tab_e2e_short` | `e7_A.json`, `e7_B.json` |

Supplementary material:

| Item | Produced by | Data |
|---|---|---|
| S1: certificate and descriptors (figure) | `reporting.figures.fig_descriptor` | `gain_curves.npz`, `tail_table.npz` |
| S2: PRBs per link (table), string water-filling (figure) | `reporting.tables.tab_ceb`, `reporting.figures.fig_waterfill` | `feas.json`, `e2.json` |
| S3: mean-square vs. per-event string stability (figure) | `reporting.figures.fig_tail` | `tail_table.npz`, `e1.json` |
| S4: planning rules, wrong burst length (tables) | `reporting.tables.tab_channel`, `reporting.tables.tab_wrongbeta` | `e5.json`, `e5_joint.json`, `e6.json` |
| S5: priority surges and loans (table) | `reporting.tables.tab_loans` | `e4_A.json`, `e4_B.json` |
| S6: comparison details (figures) | `reporting.figures.fig_compare`, `reporting.figures.fig_compare_outcome` | `e8_A.json`, `e8_B.json` |
| S7: sensitivity (table) | `reporting.tables.tab_sens` | `sens.json` |
| S8: correlated slow states (table) | `reporting.tables.tab_corr` | `e9_A.json`, `e9_B.json` |

`fig_ceb` and `tab_e2e` are additional views of the same data (a larger
version of the PRB panels and a long-format end-to-end table).

## Where the data comes from

The evaluation is a model-based simulation. It uses no field measurements
or external datasets.

- **Inputs** are model parameters only, listed in `gapslice/params.py` and
  `gapslice/channel/fsmc.py`. Standardized values come from 3GPP TS 22.186
  (platooning message rate, payload range, and the 10 ms latency and 99.99 %
  reliability of the highest level of automation, which the paper applies per
  V2V link as a baseline) and 3GPP TR 37.885 (highway V2V path loss,
  shadowing, decorrelation distance of 10 m LOS and 13 m NLOSv, and vehicle
  blockage). The truck model and CACC law follow Ploeg et al., IEEE T-ITS 2014.
- **Outputs**: every number, figure and table in the paper and its
  supplementary material is produced by this code from these inputs. Nothing
  was edited by hand.

## Comparison with published methods

`gapslice/baselines/` re-implements three published methods in the GapSlice
scenario. They are adapted implementations based on the published
algorithms, not exact reproductions. Each keeps the design choices that
define it.

| Method | What is kept | What we adapted | Information it needs |
|---|---|---|---|
| Yan and Haerri (IEEE ICC 2024) | dedicated platoon slice, TDMA with one equal slot per transmitting member, admission while slots are free, one reliability target | the tenant's preferred gap is used | platoon size, join requests |
| Zhang et al. (IEEE T-IV 2023) | control-aware scheduling with the controller and vehicle states known to the scheduler, equal bandwidth split | applied to V2V instead of V2I links; exact knapsack admission in the matched mode | controller model and vehicle states |
| Lu et al. (IEEE TNSM 2024) | one slice per tenant, bandwidth requested per slice on the slow timescale, PRBs assigned inside the slice | trained agents replaced by an ideal converged rule; requests granted in increasing size; fixed transmit power | slice target, the agent's own observations |

Every method runs in an **original** mode (its own 99.99 % targets) and a
**matched** mode (its own parameter tuned until every admitted platoon meets
the same contract). All methods use the same channel model, tenants,
controller, PRB pool, message and seeds.

## Citation

If you use this code, please cite the paper (see `CITATION.cff`).

## License

MIT, see `LICENSE`.
