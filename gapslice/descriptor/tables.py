"""Look-ups in the two control-descriptor tables (Section III-C).

Type A (certified, mean-square): the gain curves gamma(p; h, beta, eta) built
by :mod:`gapslice.descriptor.build_type_a` and stored in
``results/gain_curves.npz``. The descriptor p^A(beta; h, gamma) is the
smallest delivery probability whose certified gain is at most gamma.

Type B (per event): the brake-test counts built by
:mod:`gapslice.descriptor.build_type_b` and stored in
``results/tail_table.npz``. The descriptor p^B(beta; h, N) is the smallest
delivery probability whose 95 % Wilson upper bound of the per-event risk is
at most 1 %.
"""
import numpy as np
from functools import lru_cache
from gapslice import params as P
from gapslice import paths
from gapslice.stats import wilson

_D = None


def load_curves(path=None):
    global _D
    if _D is None:
        _D = dict(np.load(path or paths.inp("gain_curves.npz")))
    return _D


def _idx(arr, v):
    k = int(np.argmin(np.abs(np.asarray(arr) - v)))
    if abs(arr[k] - v) > 1e-6:
        raise KeyError(v)
    return k


@lru_cache(maxsize=None)
def p_c(h, beta, gamma, eta=P.ETA_DEFAULT):
    """Descriptor: smallest delivery probability with ms-gain <= gamma.
    beta=0.0 means i.i.d. losses. Returns nan if not certifiable for p<1."""
    D = load_curves()
    i, j, m = _idx(D["H"], h), _idx(D["BETAS"], beta), _idx(D["ETAS"], eta)
    q, g = D["Q"], D["G"][i, j, m]
    ok = np.isfinite(g) & (g <= gamma)
    if not ok[0]:
        return np.nan
    # largest q (lowest p) such that all smaller q are also feasible
    # (monotone interval check: first violation from the high-p side)
    k = 0
    while k + 1 < len(q) and ok[k + 1]:
        k += 1
    if k + 1 == len(q):
        return 1.0 - q[k]
    # interpolate gamma in log q between k (ok) and k+1 (not ok)
    g0, g1 = g[k], g[k + 1]
    if not np.isfinite(g1):
        return 1.0 - q[k]
    t = (gamma - g0) / (g1 - g0)
    lq = np.log(q[k]) + t * (np.log(q[k + 1]) - np.log(q[k]))
    return 1.0 - float(np.exp(lq))


def interval_ok(h, beta, gamma, eta=P.ETA_DEFAULT):
    """True if the feasible set in p is an interval [p_c, 1) on the grid."""
    D = load_curves()
    i, j, m = _idx(D["H"], h), _idx(D["BETAS"], beta), _idx(D["ETAS"], eta)
    g = D["G"][i, j, m]
    ok = np.isfinite(g) & (g <= gamma)
    # once infeasible (going to lower p) it must stay infeasible
    seen_bad = False
    for v in ok:
        if not v:
            seen_bad = True
        elif seen_bad:
            return False
    return True


# ---------------- certified gain at an arbitrary delivery probability ------
def gain_lookup(h, p, beta, eta=P.ETA_DEFAULT):
    """Certified mean-square gain, Eqs. (5) and (7), at delivery probability p,
    interpolated in log(1-p) on the stored gain curves (inf if not stable)."""
    D = load_curves()
    i, j, m = _idx(D["H"], h), _idx(D["BETAS"], beta), _idx(D["ETAS"], eta)
    q, g = D["Q"], D["G"][i, j, m]
    qq = max(1.0 - float(p), 0.0)
    if qq <= q[0]:
        return float(g[0])
    if qq >= q[-1]:
        return float(g[-1])
    k = int(np.searchsorted(q, qq)) - 1
    g0, g1 = g[k], g[k + 1]
    if not (np.isfinite(g0) and np.isfinite(g1)):
        return float(g1) if not np.isfinite(g1) else float(g0)
    t = (np.log(qq) - np.log(q[k])) / (np.log(q[k + 1]) - np.log(q[k]))
    return float(g0 + t * (g1 - g0))


def p_c_runlength(h, r, gamma, eta=P.ETA_DEFAULT):
    """Descriptor as a function of the mean loss-run length r (used only by
    the time-average planning rule): independent losses have run length
    1/p; Gilbert grid values are interpolated linearly in r on log(1-p)."""
    D = load_curves()
    betas = [float(b) for b in D["BETAS"] if b > 0]
    p_iid = p_c(h, 0.0, gamma, eta)
    if not np.isfinite(p_iid):
        return np.nan
    pts = [(1.0 / max(p_iid, 1e-9), p_iid)]
    for b in betas:
        pb = p_c(h, b, gamma, eta)
        if b > pts[-1][0]:
            pts.append((b, pb))
    if r <= pts[0][0]:
        return p_iid
    for (r0, p0), (r1, p1) in zip(pts[:-1], pts[1:]):
        if r <= r1:
            if not (np.isfinite(p0) and np.isfinite(p1)):
                return np.nan
            t = (r - r0) / (r1 - r0)
            lq = np.log(1 - p0) + t * (np.log(1 - p1) - np.log(1 - p0))
            return 1.0 - float(np.exp(lq))
    return np.nan                               # beyond the largest grid value


# ---------------- contract type B: per-event risk table ----------------
_TT = None
DELTA_B = 0.01


def load_tail_table(path=None):
    global _TT
    if _TT is None:
        _TT = dict(np.load(path or paths.inp("tail_table.npz")))
    return _TT


@lru_cache(maxsize=None)
def _risk_curve(h, beta, eta, N, upper=True):
    """Per-event risk vs loss probability on the table grid: Wilson upper
    bound (or point estimate), made non-decreasing in the loss probability."""
    T = load_tail_table()
    i, j, m, n = _idx(T["H"], h), _idx(T["BETAS"], beta), _idx(T["ETAS"], eta), _idx(T["NS"], N)
    k = T["K"][i, j, m, n].astype(float)
    R = int(T["R"])
    q = T["Q"]
    valid = k >= 0
    r = np.array([wilson(kk, R)[1] if upper else kk / R for kk in k])
    r[~valid] = np.nan
    qv, rv = q[valid], np.maximum.accumulate(r[valid])
    return qv, rv


def risk(h, p, beta, N, eta=P.ETA_DEFAULT, upper=True):
    """Per-event risk at delivery probability p (95 % upper bound by default),
    interpolated in log(1-p); loss probabilities above the grid return 1."""
    qv, rv = _risk_curve(float(h), float(beta), float(eta), int(N), upper)
    qq = max(1.0 - float(p), 1e-12)
    if qq <= qv[0]:
        return float(rv[0])
    if qq > qv[-1]:
        return 1.0
    k = int(np.searchsorted(qv, qq)) - 1
    t = (np.log(qq) - np.log(qv[k])) / (np.log(qv[k + 1]) - np.log(qv[k]))
    return float(rv[k] + t * (rv[k + 1] - rv[k]))


@lru_cache(maxsize=None)
def p_tail(h, beta, eta=P.ETA_DEFAULT, N=5, delta=DELTA_B):
    """Type-B descriptor: smallest p whose 95 % upper risk bound is <= delta
    for a platoon of N trucks (nan if not reachable on the grid)."""
    qv, rv = _risk_curve(float(h), float(beta), float(eta), int(N), True)
    ok = rv <= delta
    if not ok[0]:
        return np.nan
    k = int(np.max(np.nonzero(ok)[0]))
    if k + 1 == len(qv):
        return 1.0 - float(qv[k])
    t = (delta - rv[k]) / (rv[k + 1] - rv[k])
    lq = np.log(qv[k]) + t * (np.log(qv[k + 1]) - np.log(qv[k]))
    return 1.0 - float(np.exp(lq))
