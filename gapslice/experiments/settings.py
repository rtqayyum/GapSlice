"""Scenario settings shared by the cell-level experiments (E4, E7, E9).

E4, E7 and E9 use the same ten tenant populations: 20 tenants per cell,
admitted by the price-only gap market (Algorithm 1) on a pool of 6000
PRB-slots per CAM period.
"""
CELL_PRBS = 6000.0            # PRB-slots per CAM period in one cell
N_TENANTS = 20                # tenants per cell
POP_SEEDS = list(range(10))   # tenant populations (draw_tenants seed 4242 + s)
