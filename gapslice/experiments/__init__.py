"""Experiments of the paper and its supplementary material.

Every experiment is a module that can be run with ``python -m``; the
registry below is used by the command-line interface (``python -m gapslice``)
and by ``scripts/run_all.sh``. Times are on two CPU cores.
"""

# name: (module, contract argument needed, result files, approximate time)
REGISTRY = {
    "type-a-table": ("gapslice.descriptor.build_type_a", False, ["gain_curves.npz"], "12 min"),
    "type-b-table": ("gapslice.descriptor.build_type_b", False, ["tail_table.npz"], "85 min"),
    "feasibility": ("gapslice.experiments.feasibility", False, ["feas.json"], "< 1 min"),
    "e1": ("gapslice.experiments.e1_certificate_vs_montecarlo", False, ["e1.json"], "4 min"),
    "e2": ("gapslice.experiments.e2_string_waterfilling", False, ["e2.json"], "< 1 min"),
    "e3": ("gapslice.experiments.e3_gap_market", True, ["e3_A.json", "e3_B.json"], "5 min (A), 1 min (B)"),
    "e4": ("gapslice.experiments.e4_priority_surges", True, ["e4_A.json", "e4_B.json"], "7 min (A), 6 min (B)"),
    "e5": ("gapslice.experiments.e5_time_correlated_channel", False, ["e5.json"], "16 min"),
    "e5b": ("gapslice.experiments.e5b_joint_reservation", False, ["e5_joint.json"], "8 min"),
    "e6": ("gapslice.experiments.e6_wrong_burst_length", False, ["e6.json"], "2 min"),
    "e7": ("gapslice.experiments.e7_end_to_end", True, ["e7_A.json", "e7_B.json"], "5 min (A), 2 min (B)"),
    "e8": ("gapslice.experiments.e8_published_methods", True, ["e8_A.json", "e8_B.json"], "18 min (A), 13 min (B)"),
    "e9": ("gapslice.experiments.e9_correlated_links", True, ["e9_A.json", "e9_B.json"], "3 min (A), 2 min (B)"),
    "sensitivity": ("gapslice.experiments.sensitivity", False, ["sens.json"], "6 min"),
}
