"""Control-effective bandwidth (CEB), Section III-D.

Combines the control descriptor (:mod:`gapslice.descriptor.tables`) with the
short-packet link model (:mod:`gapslice.channel.link`) to give the PRBs that a
link or a platoon needs at a gap. Also string water-filling, Eq. (12), the
type-B CEB, Eq. (13), and the reliability-class baseline.
"""
import numpy as np
from functools import lru_cache
from gapslice import params as P
from gapslice.channel.link import design_sinr_db, prbs_for_target
from gapslice.descriptor.tables import p_c, p_tail


@lru_cache(maxsize=None)
def link_prbs(p_target, sinr_db, rice_k_db=P.RICE_K_DB, n_rx=P.N_RX):
    return prbs_for_target(p_target, sinr_db, rice_k_db=rice_k_db, n_rx=n_rx)[0]


def ceb_link(h, beta, gamma, blocked=False, eta=P.ETA_DEFAULT, eps=P.EPS_LINK_REF, **kw):
    """PRBs of one link at the eps-quantile of its large-scale SINR."""
    pc = p_c(h, beta, gamma, eta)
    if not np.isfinite(pc):
        return np.inf
    s = round(float(design_sinr_db(h, blocked, eps)), 3)
    return link_prbs(round(pc, 6), s, **kw)


def urllc_link(h, blocked=False, p_net=P.P_URLLC, eps=P.EPS_LINK_REF, **kw):
    s = round(float(design_sinr_db(h, blocked, eps)), 3)
    return link_prbs(p_net, s, **kw)


GAMMA_LADDER = P.GAMMA_UNIT ** np.arange(1, 25)   # 1.0025 .. ~1.062


def waterfill(h, beta, blocked_flags, gamma_h2t, eta=P.ETA_DEFAULT,
              gamma_max=1.03, eps=None, **kw):
    """String water-filling: choose per-link gamma_l from a ladder to minimize
    total PRBs s.t. sum log gamma_l <= log gamma_h2t and gamma_l <= gamma_max.
    Exact DP over the discretized log budget. Returns (total, gammas)."""
    lad = [float(g) for g in GAMMA_LADDER if g <= gamma_max + 1e-12]
    unit = np.log(P.GAMMA_UNIT)
    w = [int(round(np.log(g) / unit)) for g in lad]  # exact integer weights
    budget = int(np.floor(np.log(gamma_h2t) / unit + 1e-6))
    L = len(blocked_flags)
    eps = P.eps_link(L) if eps is None else eps
    cost = [[ceb_link(h, beta, g, bf, eta, eps, **kw) for g in lad] for bf in blocked_flags]
    INF = float("inf")
    dp = [INF] * (budget + 1); dp[0] = 0.0
    choice = []
    for l in range(L):
        nd = [INF] * (budget + 1); ch = [None] * (budget + 1)
        for used in range(budget + 1):
            if dp[used] == INF:
                continue
            for k, (wk, ck) in enumerate(zip(w, cost[l])):
                u2 = used + wk
                if u2 <= budget and dp[used] + ck < nd[u2]:
                    nd[u2] = dp[used] + ck; ch[u2] = (used, k)
        dp = nd; choice.append(ch)
    best = min(range(budget + 1), key=lambda u: dp[u])
    if dp[best] == INF:
        return np.inf, None
    gams, u = [], best
    for l in reversed(range(L)):
        prev, k = choice[l][u]
        gams.append(lad[k]); u = prev
    return dp[best], list(reversed(gams))


def uniform_split(h, beta, blocked_flags, gamma_h2t, eta=P.ETA_DEFAULT, eps=None, **kw):
    """Baseline: every link gets gamma_h2t^(1/L) (rounded down to the ladder)."""
    L = len(blocked_flags)
    eps = P.eps_link(L) if eps is None else eps
    j = int(np.floor(np.log(gamma_h2t) / (L * np.log(P.GAMMA_UNIT)) + 1e-6))
    if j < 1:
        return np.inf
    g = float(P.GAMMA_UNIT ** j)
    return sum(ceb_link(h, beta, g, bf, eta, eps, **kw) for bf in blocked_flags)


# ---------------- reliability classes (outcome-matched baseline) ----------
CLASSES = [0.9, 0.99, 0.999, 0.9999, 0.99999]


def rel_class(pc):
    """Smallest standard reliability class that is at least pc."""
    if not np.isfinite(pc):
        return np.nan
    for c in CLASSES:
        if c >= pc - 1e-12:
            return c
    return np.nan


def class_link(h, pc, blocked=False, eps=P.EPS_LINK_REF, **kw):
    c = rel_class(pc)
    if not np.isfinite(c):
        return np.inf
    s = round(float(design_sinr_db(h, blocked, eps)), 3)
    return link_prbs(c, s, **kw)


# ---------------- contract type B: CEB of a platoon, Eq. (13) ----------------
def ceb_tail_platoon(h, beta, blocked_flags, eta=P.ETA_DEFAULT, N=None, eps=None, **kw):
    N = len(blocked_flags) + 1 if N is None else N
    eps = P.eps_link(len(blocked_flags)) if eps is None else eps
    pt = p_tail(h, beta, eta, N)
    if not np.isfinite(pt):
        return np.inf
    tot = 0.0
    for bf in blocked_flags:
        s = round(float(design_sinr_db(h, bf, eps)), 3)
        tot += link_prbs(round(pt, 6), s, **kw)
    return tot
