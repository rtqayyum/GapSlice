"""Helpers shared by the adapted baselines."""
import numpy as np
from functools import lru_cache
from scipy.optimize import milp, LinearConstraint, Bounds
from gapslice.channel.link import design_sinr_db, mean_sinr_db
from gapslice.scenario.tenants import flags_of
from gapslice.allocation.reservation import per_link


@lru_cache(maxsize=None)
def sinr_q(h, blocked, eps):
    """Design SINR [dB] at the eps-quantile of the slow state."""
    return round(float(design_sinr_db(round(h, 3), blocked, eps)), 3)


@lru_cache(maxsize=None)
def sinr_mean(h, blocked):
    """Average SINR [dB] of a link at gap h."""
    return round(float(mean_sinr_db(round(h, 3), blocked)), 3)


def gs_links(t, h):
    """GapSlice CEB per link (string water-filling at eps/L); None if not
    certifiable at this gap."""
    try:
        n = per_link(t.contract, h, t.beta, flags_of(t), t.eta)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if all(np.isfinite(x) for x in n) else None


def knapsack(values, costs, cap):
    """0/1 knapsack solved exactly as a MILP (HiGHS)."""
    n = len(values)
    if n == 0:
        return []
    res = milp(c=-np.array(values), constraints=[LinearConstraint(np.array(costs)[None, :], -np.inf, cap)],
               integrality=np.ones(n), bounds=Bounds(0, 1), options={"time_limit": 60})
    return [bool(round(x)) for x in res.x]
