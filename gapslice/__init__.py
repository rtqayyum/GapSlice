"""GapSlice: outcome-based 6G-ready network slicing for string-stable truck platooning.

Reference implementation of the paper. The package is organised as the paper:

control/       platoon model as a Markov jump linear system, certificate (Eq. 7)
channel/       short-packet radio model and time-correlated channel
descriptor/    type-A and type-B control descriptors (build and look up)
allocation/    control-effective bandwidth, gap market (Alg. 1), loans (Alg. 2)
scenario/      tenant (platoon) population and utilities
simulation/    platoon simulators in physical units, end-to-end simulation
evaluation/    contract checks used to judge every method
baselines/     adapted published methods (Yan-Haerri, Zhang, Lu)
experiments/   E1-E9, feasibility and sensitivity studies
reporting/     figures and LaTeX tables from the stored results
"""
__version__ = "1.0.0"
