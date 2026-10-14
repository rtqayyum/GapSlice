"""Adapted Yan and Haerri (IEEE ICC 2024).

Dedicated platoon slice with deterministic TDMA: every transmitting member
gets one equal slot, platoons are admitted while slots are free (join
requests in arrival order), one URLL reliability target for the slice, fixed
gap.

* original: the slot meets 99.99 % per link (TS 22.186);
* matched : the smallest equal slot that meets the tenant's contract.
"""
import numpy as np
from functools import lru_cache
from gapslice import params as P
from gapslice.descriptor.tables import p_tail
from gapslice.allocation.ceb import link_prbs, urllc_link
from gapslice.scenario.tenants import Tenant, flags_of
from gapslice.evaluation.contract import design_ok, eps_of
from gapslice.baselines.common import sinr_q


@lru_cache(maxsize=None)
def slot_original(h, eps):
    return int(urllc_link(h, False, eps=eps))


def slot_matched(t, h):
    return _slot_matched(t.contract, h, t.beta, flags_of(t), t.eta, t.N)


@lru_cache(maxsize=None)
def _slot_matched(contract, h, beta, fl, eta, N):
    """Smallest equal slot that meets the contract for every link."""
    t = Tenant(0, N, eta, beta, fl, 1.0, contract)
    fl, eps = flags_of(t), eps_of(t)
    if t.contract == "B":
        pt = p_tail(h, t.beta, t.eta, t.N)
        return max(int(link_prbs(round(pt, 6), sinr_q(h, bf, eps))) for bf in fl) if np.isfinite(pt) else None
    lo, hi = 0, 20000
    if not design_ok(t, h, (hi,) * t.L):
        return None
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if design_ok(t, h, (mid,) * t.L):
            hi = mid
        else:
            lo = mid
    return hi


def allocate(T, pref, out, original, seed, B):
    """Admit platoons in random arrival order while equal slots are free."""
    rng = np.random.default_rng(seed)
    used = 0.0
    for k in rng.permutation(len(T)):
        t, h = T[k], pref[k]
        if h >= P.H_ACC - 1e-9:
            continue
        s = slot_original(h, eps_of(t)) if original else slot_matched(t, h)
        if s is None:
            continue
        if used + s * t.L <= B:
            out[k] = (h, tuple([s] * t.L)); used += s * t.L
    return out
