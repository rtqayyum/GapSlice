"""Feasibility check: descriptors and resources per link (Section IV-B,
supplementary Sections S1-S2).

  * interval assumption of the descriptor over the whole gain grid
  * smallest certifiable gap per burst model (types A and B)
  * descriptors p_c (type A, per-vehicle gain 1.0025^5) and p_c^B (type B,
    1 % per-event target with 95 % confidence, N = 5)
  * per-link PRBs of a link of a 5-truck platoon at its eps_l-quantile of
    the large-scale SINR (eps_l = eps/4, platoon-level availability 95 %) for
      - GapSlice CEB (reservation at p_c),
      - outcome-matched reliability class (smallest class >= p_c),
      - 99.99 % slice (our per-link application of TS 22.186)
    and whether the 99.99 % slice meets the contract at all.
  * monotonicity in the gap of the certified gain and of the per-event risk
    bound (used by the loan guard, Section III-F).

Usage:  python -m gapslice.experiments.feasibility
Output: results/feas.json
"""
import json
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.descriptor.tables import load_curves, load_tail_table, p_c, p_tail, interval_ok
from gapslice.allocation.ceb import ceb_link, urllc_link, class_link, rel_class, link_prbs, GAMMA_LADDER
from gapslice.stats import wilson
from gapslice.channel.link import design_sinr_db

D = load_curves()
T = load_tail_table()
H = [float(h) for h in D["H"] if h < P.H_ACC - 1e-9]
BETAS = [0.0, 2.0, 4.0]
BNAME = {0.0: "iid", 2.0: "burst2", 4.0: "burst4"}


def fin(x):
    return None if (x is None or not np.isfinite(x)) else float(x)


def b_link(h, p, blocked=False):
    if not np.isfinite(p):
        return np.inf
    return link_prbs(round(float(p), 6), round(float(design_sinr_db(h, blocked)), 3))


if __name__ == "__main__":
    out = {"H": H, "gamma_link": P.GAMMA_LINK}

    # ---- interval assumption over the full certified-gain grid ----
    viol, n = [], 0
    for h in [float(x) for x in D["H"]]:
        for b in [float(x) for x in D["BETAS"]]:
            for eta in D["ETAS"]:
                for g in GAMMA_LADDER:
                    n += 1
                    if not interval_ok(h, b, float(g), float(eta)):
                        viol.append((h, b, float(eta), float(g)))
    out["interval_checks"], out["interval_violations"] = n, viol

    # ---- smallest certifiable gap ----
    out["h_min_A"], out["h_min_B"] = {}, {}
    for b in BETAS:
        fa = [h for h in H if np.isfinite(p_c(h, b, P.GAMMA_LINK))]
        fb = [h for h in [float(x) for x in T["H"]] if np.isfinite(p_tail(h, b, P.ETA_DEFAULT, 5))]
        out["h_min_A"][BNAME[b]] = min(fa) if fa else None
        out["h_min_B"][BNAME[b]] = min(fb) if fb else None

    # ---- descriptors and per-link PRBs ----
    rows = []
    for b in BETAS:
        for h in H:
            pa = p_c(h, b, P.GAMMA_LINK)
            pb = p_tail(h, b, P.ETA_DEFAULT, 5) if h in [float(x) for x in T["H"]] else np.nan
            url = float(urllc_link(h))
            r = dict(beta=BNAME[b], h=h, urllc=url,
                     p_A=fin(pa), ceb_A=fin(b_link(h, pa)), class_A=fin(rel_class(pa)),
                     cls_A=fin(class_link(h, pa)),
                     urllc_meets_A=bool(np.isfinite(pa) and pa <= P.P_URLLC),
                     p_B=fin(pb), ceb_B=fin(b_link(h, pb)), class_B=fin(rel_class(pb)),
                     cls_B=fin(class_link(h, pb)),
                     urllc_meets_B=bool(np.isfinite(pb) and pb <= P.P_URLLC))
            # blocked (NLOSv) link
            r["urllc_blk"] = float(urllc_link(h, True))
            # per-link availability of 95 % (eps = 5 % per link): what the
            # platoon-level availability costs
            r["ceb_A_eps5"] = fin(link_prbs(round(float(pa), 6), round(float(design_sinr_db(h, False, P.EPS_LS)), 3))
                                  if np.isfinite(pa) else np.inf)
            r["urllc_eps5"] = float(urllc_link(h, eps=P.EPS_LS))
            r["ceb_A_blk"] = fin(b_link(h, pa, True))
            r["cls_A_blk"] = fin(class_link(h, pa, True))
            rows.append(r)
    out["rows"] = rows

    # ---- monotonicity in the gap (loan guard) ----
    G = D["G"]                                   # (H, BETAS, ETAS, Q)
    HH = [float(x) for x in D["H"]]
    pairs = viol_g = 0
    worst_g = 0.0
    for j in range(G.shape[1]):
        for m in range(G.shape[2]):
            for k in range(G.shape[3]):
                for i in range(len(HH) - 1):
                    g0, g1 = G[i, j, m, k], G[i + 1, j, m, k]
                    if np.isnan(g0) or np.isnan(g1):
                        continue
                    pairs += 1
                    if not np.isfinite(g0):
                        continue                     # unstable at the shorter gap
                    if (not np.isfinite(g1)) or g1 > g0 * (1 + 1e-6):
                        viol_g += 1
                        worst_g = max(worst_g, (g1 - g0) / g0 if np.isfinite(g1) else np.inf)
    out["mono_gain"] = dict(pairs=pairs, violations=viol_g, worst_rel=worst_g)
    # per-event risk table: 95 % upper bound and significant reversals
    K, R = T["K"], int(T["R"])
    pairs_r = viol_r = sig_r = 0
    worst_r = 0.0
    for j in range(K.shape[1]):
        for m in range(K.shape[2]):
            for n_ in range(K.shape[3]):
                for k in range(K.shape[4]):
                    for i in range(K.shape[0] - 1):
                        a, c = K[i, j, m, n_, k], K[i + 1, j, m, n_, k]
                        if a < 0 or c < 0:
                            continue
                        pairs_r += 1
                        ua, uc = wilson(a, R)[1], wilson(c, R)[1]
                        if uc > ua + 1e-12:
                            viol_r += 1
                            worst_r = max(worst_r, uc - ua)
                            # reversal larger than sampling noise: intervals disjoint
                            if wilson(c, R)[0] > wilson(a, R)[1]:
                                sig_r += 1
    out["mono_risk"] = dict(pairs=pairs_r, violations=viol_r, significant=sig_r, worst_abs=worst_r)

    json.dump(out, open(paths.out("feas.json"), "w"), indent=1)

    # ---- console summary ----
    print("interval violations:", len(viol), "of", n)
    print("h_min A:", out["h_min_A"], " B:", out["h_min_B"])
    print("monotonicity gain:", out["mono_gain"], " risk:", out["mono_risk"])
    for b in BETAS:
        print(f"\n{BNAME[b]}: h | p_A ceb_A cls_A | p_B ceb_B cls_B | 99.99% (meets A/B)")
        for r in rows:
            if r["beta"] != BNAME[b]:
                continue
            f = lambda x, d=0: "-" if x is None else f"{x:.{d}f}"
            print(f"  {r['h']:.2f} | {f(r['p_A'],4)} {f(r['ceb_A'])} {f(r['cls_A'])} | "
                  f"{f(r['p_B'],4)} {f(r['ceb_B'])} {f(r['cls_B'])} | {r['urllc']:.0f} "
                  f"({r['urllc_meets_A']}/{r['urllc_meets_B']})")
