"""Adapted Lu et al. (IEEE TNSM 2024).

One slice per tenant (critical-message V2V slice). On the long timescale each
slice agent requests bandwidth for its SLA (reliability target) from its own
state; on the short timescale PRBs are assigned within the slice to meet the
per-link reliability. We do not train the agents: each agent is replaced by
an ideal converged rule that requests the PRBs meeting its target at the
average SINR of each link (finite-blocklength model). The paper does not
specify how over-subscription is resolved; we grant requests in increasing
size while capacity remains. Transmit power is fixed in our scenario, so
power control is not used.

* original: 99.99 % per link at the average SINR;
* matched : one reliability target per slice (the smallest that meets the
  contract), every link sized at its eps_l-quantile.
"""
import numpy as np
from gapslice import params as P
from gapslice.descriptor.tables import p_c, p_tail
from gapslice.allocation.ceb import link_prbs
from gapslice.scenario.tenants import flags_of
from gapslice.evaluation.contract import eps_of
from gapslice.baselines.common import sinr_q, sinr_mean


def links_original(t, h):
    """Ideal converged request (original target 99.99 %) at the average SINR of each link."""
    return tuple(int(link_prbs(P.P_URLLC, sinr_mean(h, bf))) for bf in flags_of(t))


def links_matched(t, h):
    """One reliability target per slice (smallest that meets the contract),
    every link sized at its eps_l-quantile."""
    eps = eps_of(t)
    r = p_c(h, t.beta, P.GAMMA_LINK, t.eta) if t.contract == "A" else p_tail(h, t.beta, t.eta, t.N)
    if not np.isfinite(r):
        return None
    return tuple(int(link_prbs(round(r, 6), sinr_q(h, bf, eps))) for bf in flags_of(t))


def allocate(T, pref, out, original, B):
    """Grant the slice requests in increasing size while capacity remains."""
    req = []
    for k, t in enumerate(T):
        h = pref[k]
        if h >= P.H_ACC - 1e-9:
            continue
        n = links_original(t, h) if original else links_matched(t, h)
        if n is None:
            continue
        req.append((sum(n), k, n))
    used = 0.0
    for tot, k, n in sorted(req):
        if used + tot <= B:
            out[k] = (pref[k], n); used += tot
    return out
