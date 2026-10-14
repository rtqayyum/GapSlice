"""Check whether a reservation meets a tenant's contract.

Used to judge every allocation method in the same way (E8): the contracted
metric is evaluated from the tenant's descriptor tables at the delivery
probability that the reservation gives in each large-scale channel state.

* :func:`contract_ok`  frozen-state contract (type A: certified head-to-tail
  gain, Eq. (6); type B: 95 % upper per-event risk <= 1 %)
* :func:`availability` share of stationary large-scale states in which the
  contract holds (platoon-level availability, Eq. (9))
* :func:`design_ok`    contract at the per-link eps_l-quantile (the planning
  point)
"""
import numpy as np
from functools import lru_cache
from gapslice import params as P
from gapslice.descriptor.tables import load_curves, _idx, _risk_curve
from gapslice.scenario.tenants import flags_of
from gapslice.allocation.reservation import p_of
from gapslice.simulation import end_to_end as E2E

N_MC = 40000                                    # availability samples per platoon


def eps_of(t):
    """Per-link outage share eps/L of a tenant's platoon."""
    return P.eps_link(t.L)


@lru_cache(maxsize=None)
def gain_curve(h, beta, eta):
    """(log q grid, gain) of the certificate, inf where not certifiable."""
    D = load_curves()
    i, j, m = _idx(D["H"], h), _idx(D["BETAS"], beta), _idx(D["ETAS"], eta)
    g = np.array(D["G"][i, j, m], dtype=float)
    g[~np.isfinite(g)] = np.inf
    return np.log(D["Q"]), g


def gain_vec(h, beta, eta, p):
    lq, g = gain_curve(h, beta, eta)
    q = np.clip(1.0 - np.asarray(p, dtype=float), 1e-12, 1.0)
    with np.errstate(invalid="ignore"):
        out = np.interp(np.log(q), lq, g)
    out[~np.isfinite(out)] = np.inf
    out[np.log(q) > lq[-1]] = np.inf                  # beyond the grid: not certified
    if beta > 0:
        out[np.asarray(p) < 1.0 / (1.0 + beta)] = np.inf
    return out


def risk_vec(h, beta, eta, N, p):
    qv, rv = _risk_curve(float(h), float(beta), float(eta), int(N), True)
    q = np.clip(1.0 - np.asarray(p, dtype=float), 1e-12, 1.0)
    out = np.interp(np.log(q), np.log(qv), rv)
    out[q > qv[-1]] = 1.0
    if beta > 0:
        out[np.asarray(p) < 1.0 / (1.0 + beta)] = 1.0
    return out


def contract_ok(t, h, p):
    """p: array (..., L) of delivery probabilities -> boolean contract met."""
    if t.contract == "A":
        g = np.prod(gain_vec(h, t.beta, t.eta, p.reshape(-1)).reshape(p.shape), axis=-1)
        return g <= P.GAMMA_LINK ** t.L * (1 + 1e-9)
    r = risk_vec(h, t.beta, t.eta, t.N, p.min(axis=-1))
    return r <= 0.01 + 1e-12


_Z = None


def mc_samples():
    global _Z
    if _Z is None:
        _Z = np.random.default_rng(2024).standard_normal((N_MC, 6))
    return _Z


def availability(t, h, n):
    """Share of (stationary, independent) large-scale states in which the
    frozen-state contract of the platoon holds with per-link PRBs n."""
    Z = mc_samples()[:, :t.L]
    p = np.column_stack([np.interp(Z[:, l], E2E.XG, E2E.p_curve(int(n[l]), round(h, 2), bf))
                         for l, bf in enumerate(flags_of(t))])
    return float(np.mean(contract_ok(t, h, p)))


def design_ok(t, h, n):
    """Contract at the per-link eps_l-quantile (the planning point)."""
    p = np.array([[p_of(int(x), round(h, 3), bf, eps_of(t)) if x > 0 else 0.0
                   for x, bf in zip(n, flags_of(t))]])
    return bool(contract_ok(t, h, p)[0])
