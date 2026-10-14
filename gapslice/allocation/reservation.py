"""Per-link PRB reservation of an admitted platoon.

At gap h, every link of a type-A platoon gets the CEB of its share of the
gain budget chosen by string water-filling, Eq. (12); every link of a type-B
platoon gets the PRBs that reach the type-B descriptor, Eq. (13). Links are
planned at the eps/L quantile of their large-scale SINR, Eq. (9).
"""
from functools import lru_cache
from gapslice import params as P
from gapslice.channel.link import design_sinr_db, prob_from_prbs
from gapslice.descriptor.tables import p_tail
from gapslice.allocation.ceb import waterfill, ceb_link, link_prbs


@lru_cache(maxsize=None)
def sinr(h, blocked, eps):
    """Design SINR [dB] of a link at gap h (eps-quantile of the slow state)."""
    return round(float(design_sinr_db(round(h, 3), blocked, eps)), 3)


@lru_cache(maxsize=None)
def p_of(n, h, blocked, eps):
    """Delivery probability at the eps-quantile with n PRBs at gap h."""
    if n <= 0:
        return 0.0
    return prob_from_prbs(int(n), sinr(h, blocked, eps))


@lru_cache(maxsize=None)
def per_link(contract, h, beta, flags, eta):
    """Per-link reservation at gap h (flags sorted, blocked first)."""
    L = len(flags)
    eps = P.eps_link(L)
    if h >= P.H_ACC - 1e-9:
        return tuple([0] * L)
    if contract == "B":
        pt = p_tail(h, beta, eta, L + 1)
        return tuple(int(link_prbs(round(pt, 6), sinr(h, bf, eps))) for bf in flags)
    tot, gams = waterfill(h, beta, flags, P.GAMMA_LINK ** L, eta, eps=eps)
    return tuple(int(ceb_link(h, beta, g, bf, eta, eps)) for g, bf in zip(gams, flags))
