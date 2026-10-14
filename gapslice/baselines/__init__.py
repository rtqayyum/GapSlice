"""Adapted implementations of three published methods (Section IV-F).

The methods are re-implemented in the GapSlice scenario (same channel model,
platoon sizes, truck dynamics and controller, tenants, PRB pool, message size
and deadline, availability and string-stability targets, and random seeds).
They are adaptations based on the published algorithms, not exact
reproductions; each keeps the design choices that define it.

Every method runs in two modes:
  original : the method's own objective and parameters (99.99 % per link,
             TS 22.186), measured against the contract;
  matched  : the method's own parameter tuned until it meets the same
             contract (string stability and 95 % platoon-level availability).
GapSlice (Algorithm 1 with CEB menus) and the full-information optimum of P1
are the reference.
"""
from gapslice import params as P
from gapslice.allocation.market import price_only_market, oracle
from gapslice.baselines import yan_harri, zhang, lu
from gapslice.baselines.common import gs_links

METHODS = ["GapSlice", "Yan-Harri (original)", "Yan-Harri (matched)", "Zhang (original)",
           "Zhang (matched)", "Lu (original)", "Lu (matched)", "Oracle"]
INFO = {"GapSlice": "descriptor tables, menu choices",
        "Yan-Harri": "platoon size, join requests",
        "Zhang": "controller model and vehicle states (full)",
        "Lu": "per-slice SLA and observations (learned policy)",
        "Oracle": "full information"}


def allocate(T, method, seed, B):
    """Per tenant: (gap, per-link PRBs) for a policy (gap = H_ACC: no V2V)."""
    acc = lambda t: (P.H_ACC, tuple([0] * t.L))
    if method in ("GapSlice", "Oracle"):
        ch = price_only_market(T, B, "ceb", seed=seed) if method == "GapSlice" else oracle(T, B, "ceb")
        return [acc(t) if c[0] >= P.H_ACC - 1e-9 else (c[0], gs_links(t, c[0])) for t, c in zip(T, ch)]
    pref = [t.h_pref_urllc() for t in T]
    out = [acc(t) for t in T]
    if method.startswith("Yan"):
        return yan_harri.allocate(T, pref, out, original="original" in method, seed=seed, B=B)
    if method == "Zhang (original)":
        return zhang.allocate_original(T, pref, out, B)
    if method == "Zhang (matched)":
        return zhang.allocate_matched(T, pref, out, B)
    if method.startswith("Lu"):
        return lu.allocate(T, pref, out, original="original" in method, B=B)
    raise ValueError(method)
