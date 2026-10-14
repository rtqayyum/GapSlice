# Code architecture

The package follows the structure of the paper. Lower layers never import
higher ones, so each part can be used and tested on its own.

```
                 params.py  paths.py  stats.py
                             |
        +--------------------+---------------------+
        |                                          |
    control/                                   channel/
    mjls.py         CACC follower as an MJLS   link.py   path loss, SINR, finite-
    certificate.py  bounded-real-lemma SDP               blocklength delivery with
    montecarlo.py   Monte Carlo gain                     blind retransmissions
        |                                      fsmc.py   slow-state Markov channel,
        |                                                joint certificate, traces
        +--------------------+---------------------+
                             |
                       descriptor/
                       build_type_a.py   certified gain curves (type A)
                       build_type_b.py   brake-test risk table (type B)
                       tables.py         p^A, p^B and risk look-ups
                             |
                       allocation/
                       ceb.py            control-effective bandwidth, water-filling
                       reservation.py    per-link reservation of a platoon
                       market.py         price-only gap market (Alg. 1), optimum
                       loans.py          stability loans with loan clause (Alg. 2)
                             |
        +--------------------+---------------------+
        |                    |                     |
    scenario/           simulation/           evaluation/
    tenants.py          platoon.py            contract.py   contract and
    population,         vectorized.py                       availability checks
    menus, utility      end_to_end.py
        |                    |                     |
        +--------------------+---------------------+
                             |
                       baselines/        Yan-Haerri, Zhang, Lu (adapted)
                             |
                       experiments/      E1-E9, feasibility, sensitivity
                             |
                       reporting/        figures.py, tables.py
```

## Paper to code

| Paper | Module |
|---|---|
| Truck model and CACC law, Eqs. (1)-(2) | `gapslice.control.mjls` (`zoh_coeffs`, `mode_matrices`) |
| Gilbert losses, Eq. (3); jump-system model, Eq. (4) | `gapslice.control.mjls` (`tpm`, `mode_matrices`) |
| Mean-square string gain, Eq. (5); certificate, Eq. (7) | `gapslice.control.mjls.ms_gain`, `gapslice.control.certificate.GainSolver` |
| Type-A descriptor, Eq. (8) | `gapslice.descriptor.build_type_a`, `gapslice.descriptor.tables.p_c` |
| Type-B descriptor | `gapslice.descriptor.build_type_b`, `gapslice.descriptor.tables.p_tail` |
| Platoon availability, Eq. (9) | `gapslice.params.eps_link` |
| Finite-blocklength delivery, Eqs. (10)-(11) | `gapslice.channel.link` |
| Slow-state channel and joint certificate | `gapslice.channel.fsmc` |
| CEB with string water-filling, Eq. (12); type-B CEB, Eq. (13) | `gapslice.allocation.ceb` |
| Problem P1, Eq. (14); Algorithm 1 | `gapslice.allocation.market` |
| Loan clause, Eq. (15); Algorithm 2 | `gapslice.allocation.loans` |
| Tenant population and utility | `gapslice.scenario.tenants` |
| Adapted published methods (Section IV-F) | `gapslice.baselines` |
| End-to-end validation (Section IV-G) | `gapslice.simulation.end_to_end`, `gapslice.experiments.e7_end_to_end` |

## Where files go

All reads and writes go through `gapslice.paths`. Stored results are read
from `results/`. New files go to `results/`, `figures/` and `tables/`, or to
`$GAPSLICE_OUTPUT/...` when that variable is set, so a full re-run can be
compared with the stored files without overwriting them.
