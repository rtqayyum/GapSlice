"""End-to-end platoon simulation on a continuous time-correlated channel.

Used by the end-to-end validation (E7), the comparison with published
methods (E8) and the correlated-links experiment (E9).

The channel is NOT the finite-state model used for planning: each link has
its own continuous Gauss-Markov large-scale process (TR 37.885
decorrelation distance, 10 m LOS, 13 m NLOSv), fast fading enters through
the short-packet delivery probability of the reservation at the current
large-scale SINR, and losses within a slow state follow the tenant's declared
burst length. Outage states are included. A hard brake of the leader happens
at a random time in every run.

Reservation rules for the same admitted gaps:
  GapSlice         per-link outage share eps/L (platoon-level availability
                   1 - eps by the union bound) -- the rule of the paper
  per-link eps     every link planned at its own 95 % availability
                   (platoon-level availability not controlled)
  99.99 % slice    99.99 % per link at the same per-link share eps/L
"""
import numpy as np
from functools import lru_cache
from gapslice import params as P
from gapslice.channel import fsmc as CT
from gapslice.channel.link import design_sinr_db, mean_sinr_db, prob_from_prbs
from gapslice.descriptor.tables import p_c, p_tail
from gapslice.allocation.ceb import waterfill, ceb_link, link_prbs, urllc_link
from gapslice.scenario.tenants import flags_of
from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics

R = 600                                   # Monte Carlo runs per platoon
S_LEN = int(12 / P.T)                     # 12 s horizon
RULES = ["GapSlice", "per-link eps", "99.99% slice"]
XG = np.linspace(-6.0, 6.0, 121)          # grid of x / sigma for p(x)


@lru_cache(maxsize=None)
def reservation(contract, h, beta, flags, eta, rule):
    """Per-link PRBs and per-link delivery targets (p_c or p_tail)."""
    L = len(flags)
    eps = P.EPS_LS if rule == "per-link eps" else P.eps_link(L)
    if rule == "99.99% slice":
        n = tuple(int(urllc_link(h, bf, eps=eps)) for bf in flags)
    elif contract == "B":
        pt = p_tail(h, beta, eta, L + 1)
        n = tuple(int(link_prbs(round(pt, 6), round(float(design_sinr_db(h, bf, eps)), 3))) for bf in flags)
    else:
        tot, gams = waterfill(h, beta, flags, P.GAMMA_LINK ** L, eta, eps=eps)
        n = tuple(int(ceb_link(h, beta, g, bf, eta, eps)) for g, bf in zip(gams, flags))
    # delivery target of each link: the contract's own descriptor (for type A
    # with the per-link gain budget chosen by water-filling under this rule)
    if contract == "B":
        tgt = tuple([p_tail(h, beta, eta, L + 1)] * L)
    else:
        e2 = P.EPS_LS if rule == "per-link eps" else P.eps_link(L)
        tot, gams = waterfill(h, beta, flags, P.GAMMA_LINK ** L, eta, eps=e2)
        tgt = tuple(p_c(h, beta, g, eta) for g in gams)
    return n, tgt


@lru_cache(maxsize=None)
def p_curve(n, h, blocked):
    """Delivery probability of n PRBs vs the large-scale deviation x (grid)."""
    sig = CT.sigma_ls(blocked)
    s0 = mean_sinr_db(h, blocked)
    return np.array([prob_from_prbs(int(n), s0 + sig * z) for z in XG])


def link_avail(n, h, blocked, target):
    """Exact share of time in which the link meets its target: Pr[z >= z*],
    p(z*) = target, on the stationary Gauss-Markov process."""
    from scipy.stats import norm
    pc = p_curve(n, h, blocked)
    ok = pc >= target - 1e-12
    if not ok.any():
        return 0.0
    i = int(np.argmax(ok))
    if i == 0:
        return 1.0
    z0, z1, p0, p1 = XG[i - 1], XG[i], pc[i - 1], pc[i]
    zs = z0 + (target - p0) * (z1 - z0) / max(p1 - p0, 1e-15)
    return float(norm.sf(zs))


def link_trace(n, h, blocked, beta, target, rng, runs=None):
    """Delivery indicators (S, R) and indicator that the link meets its
    target (S, R), on a continuous Gauss-Markov large-scale process.
    ``runs`` overrides the number of runs R."""
    R_ = R if runs is None else runs
    sig = CT.sigma_ls(blocked)
    rho = CT.rho_of(CT.DC_NLOSV if blocked else CT.DC_LOS)
    pc = p_curve(n, h, blocked)
    z = rng.standard_normal(R_)                      # stationary start (in sigma units)
    good = np.ones(R_, dtype=bool)
    d = np.zeros((S_LEN, R_), dtype=bool)
    ok = np.zeros((S_LEN, R_), dtype=bool)
    sd = np.sqrt(1 - rho ** 2)
    for t in range(S_LEN):
        z = rho * z + sd * rng.standard_normal(R_)
        p = np.interp(z, XG, pc)
        ok[t] = p >= target - 1e-12
        v = rng.random(R_)
        if beta > 0:
            rb = np.minimum(1.0 / beta, p / np.maximum(1 - p, 1e-12))
            alpha = np.minimum(1.0, rb * (1 - p) / np.maximum(p, 1e-12))
            dl = np.where(good, v >= alpha, v < rb)
        else:
            dl = v < p
        good = dl
        d[t] = dl
    return d, ok


def simulate(t, h, rule, seed):
    """Monte Carlo of one admitted platoon under a reservation rule."""
    fl = flags_of(t)
    n, tgt = reservation(t.contract, h, t.beta, fl, t.eta, rule)
    rng = np.random.default_rng(seed)
    u0, starts = braking_pulse(S_LEN, R, rng, 2.0, 6.0)
    D = np.zeros((S_LEN, R, t.L), dtype=bool)
    OK = np.ones((S_LEN, R), dtype=bool)
    exact = 1.0
    for l, (nl, bf, pt) in enumerate(zip(n, fl, tgt)):
        d, ok = link_trace(nl, h, bf, t.beta, pt, rng)
        D[:, :, l] = d
        OK &= ok
        exact *= link_avail(nl, h, bf, pt)
    m = disturbance_metrics(u0, t.N, np.full(S_LEN, h), None, [t.beta] * t.L, t.eta,
                            seed=seed + 1, deltas=D)
    avail_brake = OK[starts, np.arange(R)]          # all links meet their targets at the brake onset
    ev = m["peak_growth"] > 1.05
    return dict(prbs=int(sum(n)), avail=float(OK.mean()), avail_exact=exact, n=R, k=int(ev.sum()),
                n_av=int(avail_brake.sum()), k_av=int(ev[avail_brake].sum()),
                n_out=int((~avail_brake).sum()), k_out=int(ev[~avail_brake].sum()),
                dmin=m["dmin"].tolist(), ms_amp=float(np.sqrt(np.mean(m["amp"] ** 2))),
                gamma_contract=P.GAMMA_LINK ** t.L)
