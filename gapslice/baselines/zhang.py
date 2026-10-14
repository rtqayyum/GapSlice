"""Adapted Zhang et al. (IEEE T-IV 2023).

Control-aware scheduling with full information (controller and vehicle
state known to the scheduler), fixed gap.

* original: bandwidth split equally among the vehicles (B/M);
* matched : every platoon gets exactly the PRBs its contract needs at its
  preferred gap (the GapSlice CEB, which the full-information scheduler can
  compute), and platoons are admitted by an exact knapsack on utility.
"""
from gapslice import params as P
from gapslice.baselines.common import gs_links, knapsack


def allocate_original(T, pref, out, B):
    cand = [k for k in range(len(T)) if pref[k] < P.H_ACC - 1e-9]
    M = sum(T[k].L for k in cand)
    share = int(B // max(M, 1))
    for k in cand:
        out[k] = (pref[k], tuple([share] * T[k].L))
    return out


def allocate_matched(T, pref, out, B):
    cand, vals, costs, links = [], [], [], []
    for k, t in enumerate(T):
        h = pref[k]
        if h >= P.H_ACC - 1e-9:
            continue
        n = gs_links(t, h)
        if n is None:
            continue
        cand.append(k); links.append(n)
        vals.append(t.U(h) - t.U(P.H_ACC)); costs.append(float(sum(n)))
    for k, n, x in zip(cand, links, knapsack(vals, costs, B)):
        if x:
            out[k] = (pref[k], n)
    return out
