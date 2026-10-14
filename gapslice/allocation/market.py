"""Admission policies for one cell.

  price_only_market : Algorithm 1 of the paper. Tenants reveal only their
                      menu choice at prices posted by the operator.
                      Phase 1: bisection on one price until the reported
                      demand fits the pool (ascending clock).
                      Phase 2: the residual capacity is offered with a
                      descending clock; a tenant may only pick an upgrade
                      that still fits.
  oracle            : exact optimum of P1 (full information, MILP).
  greedy_fixed      : CEB-fixed and 99.99 %-fixed baselines.
  equal_share       : equal split of the pool.
"""
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from gapslice import params as P
def evaluate(tenants, choice, B):
    """choice[k] = (h, b, U). Returns metrics."""
    U = sum(c[2] for c in choice)
    used = sum(c[1] for c in choice)
    cacc = sum(1 for c in choice if c[0] < P.H_ACC)
    gaps = [c[0] for c in choice]
    return dict(utility=float(U), used=float(used), util_frac=float(used / B),
                cacc=int(cacc), cacc_frac=cacc / len(tenants),
                mean_gap=float(np.mean(gaps)), feasible=bool(used <= B + 1e-6))


def _best(menu, lam, allowed=None):
    """Tenant-side best response: argmax_h U(h) - lam*b(h) (private U)."""
    best, bi = -np.inf, None
    for i, (h, b, u) in enumerate(menu):
        if allowed is not None and not allowed(i):
            continue
        v = u - lam * b
        if v > best + 1e-15:
            best, bi = v, i
    return bi


def price_only_market(tenants, B, kind="ceb", J1=40, J2=64, seed=0,
                      return_info=False):
    """Algorithm 1 (price-only gap market)."""
    menus = [t.menu(kind) for t in tenants]
    rounds = 0

    def demand(lam):
        idx = [_best(m, lam) for m in menus]
        return idx, sum(menus[k][i][1] for k, i in enumerate(idx))

    # ---- Phase 1: clearing price -------------------------------------
    lam_lo = 0.0
    idx0, d0 = demand(0.0); rounds += 1
    if d0 <= B:
        idx, lam_hi = idx0, 0.0
    else:
        umax = max(m[0][2] for m in menus)
        lam_hi = umax / max(B, 1.0)
        idx, d = demand(lam_hi); rounds += 1
        while d > B:
            lam_lo, lam_hi = lam_hi, 2 * lam_hi
            idx, d = demand(lam_hi); rounds += 1
        for _ in range(J1):
            lam = 0.5 * (lam_lo + lam_hi)
            i2, d2 = demand(lam); rounds += 1
            if d2 > B:
                lam_lo = lam
            else:
                lam_hi, idx = lam, i2
    R = B - sum(menus[k][i][1] for k, i in enumerate(idx))
    # ---- Phase 2: residual capacity, descending clock -------------------
    rng = np.random.default_rng(seed)
    if lam_hi > 0 and R > 0:
        for j in range(1, J2 + 1):
            lam = lam_hi * (1 - j / J2)
            rounds += 1
            for k in rng.permutation(len(menus)):
                cur = idx[k]
                bcur = menus[k][cur][1]
                nb = _best(menus[k], lam,
                           allowed=lambda i, k=k, bcur=bcur: menus[k][i][1] - bcur <= R + 1e-9)
                if nb is not None and menus[k][nb][1] > bcur + 1e-9:
                    R -= menus[k][nb][1] - bcur
                    idx[k] = nb
    choice = [menus[k][i] for k, i in enumerate(idx)]
    if return_info:
        return choice, dict(rounds=rounds, price=lam_hi, residual=R)
    return choice


def oracle(tenants, B, kind="ceb"):
    """Exact optimum of P1 (full information) via MILP."""
    menus = [t.menu(kind) for t in tenants]
    c, A_cap, var = [], [], []
    for k, m in enumerate(menus):
        for i, (h, b, u) in enumerate(m):
            var.append((k, i)); c.append(-u); A_cap.append(b)
    nv = len(var)
    A_one = np.zeros((len(menus), nv))
    for v, (k, i) in enumerate(var):
        A_one[k, v] = 1.0
    cons = [LinearConstraint(np.array(A_cap)[None, :], -np.inf, B),
            LinearConstraint(A_one, 1, 1)]
    res = milp(c=np.array(c), constraints=cons, integrality=np.ones(nv),
               bounds=Bounds(0, 1), options={"time_limit": 60})
    x = np.round(res.x).astype(int)
    choice = [None] * len(menus)
    for v, (k, i) in enumerate(var):
        if x[v] == 1:
            choice[k] = menus[k][i]
    return choice


def _acc(t):
    return (P.H_ACC, 0.0, t.U(P.H_ACC))


def greedy_fixed(tenants, B, mode):
    """CEB-fixed / 99.99 %-fixed: each tenant asks for its preferred gap
    (smallest gap that a 99.99 % link meets); the operator admits by utility
    gain per PRB (full information); rejected tenants drive in ACC."""
    req = []
    for t in tenants:
        h = t.h_pref_urllc()
        if h >= P.H_ACC:
            req.append(None); continue
        b = t.urllc_demand(h) if mode == "urllc" else t.demand(h, "ceb")
        req.append((h, b, t.U(h)))
    order = sorted(range(len(tenants)),
                   key=lambda k: -np.inf if req[k] is None else
                   -(req[k][2] - tenants[k].U(P.H_ACC)) / max(req[k][1], 1e-9))
    used, choice = 0.0, [None] * len(tenants)
    for k in order:
        r = req[k]
        if r is not None and np.isfinite(r[1]) and used + r[1] <= B:
            choice[k] = r; used += r[1]
        else:
            choice[k] = _acc(tenants[k])
    return choice


def equal_share(tenants, B, kind="ceb"):
    share = B / len(tenants)
    choice = []
    for t in tenants:
        opts = [o for o in t.menu(kind) if o[1] <= share]
        choice.append(min(opts, key=lambda o: o[0]))
    return choice
