# Stored results

These are the exact result files used in the paper. Every figure in
`figures/` and every table in `tables/` is drawn from them by
`python -m gapslice figures` and `python -m gapslice tables`. The `.log` files
are the console output of the runs that produced them.

| File | Produced by | Content |
|---|---|---|
| `gain_curves.npz` | `gapslice.descriptor.build_type_a` | certified mean-square gain on a grid of gap, burst length, driveline constant and delivery probability (type-A descriptor) |
| `tail_table.npz` | `gapslice.descriptor.build_type_b` | brake-test counts on a grid of gap, burst length, driveline constant, platoon size and loss probability (type-B descriptor, loan guard) |
| `feas.json` | `gapslice.experiments.feasibility` | interval check, smallest certifiable gaps, descriptors, PRBs per link vs. classes and 99.99 % slice, monotonicity |
| `e1.json` | `gapslice.experiments.e1_certificate_vs_montecarlo` | certificate vs. Monte Carlo gain, per-event risk vs. delivery probability |
| `e2.json` | `gapslice.experiments.e2_string_waterfilling` | string water-filling vs. uniform split vs. 99.99 % slice |
| `e3_A.json`, `e3_B.json` | `gapslice.experiments.e3_gap_market` | gap market vs. optimum and baselines, 100 populations per load |
| `e4_A.json`, `e4_B.json` | `gapslice.experiments.e4_priority_surges` | priority surges: service over time, loan clause checks, lender Monte Carlo, clause sweep |
| `e5.json` | `gapslice.experiments.e5_time_correlated_channel` | loss rate and burstiness vs. reservation, planning rules on a time-correlated channel |
| `e5_joint.json` | `gapslice.experiments.e5b_joint_reservation` | smallest reservation that meets the joint certificate |
| `e6.json` | `gapslice.experiments.e6_wrong_burst_length` | wrong declared burst length, online HARQ check, probation gap |
| `e7_A.json`, `e7_B.json` | `gapslice.experiments.e7_end_to_end` | end-to-end validation from admission to braking |
| `e8_A.json`, `e8_B.json` | `gapslice.experiments.e8_published_methods` | comparison with adapted Yan-Haerri, Zhang and Lu methods |
| `e9_A.json`, `e9_B.json` | `gapslice.experiments.e9_correlated_links` | correlated slow states across the links of a platoon |
| `sens.json` | `gapslice.experiments.sensitivity` | payload, tolerance, radio and channel-model sensitivity |
