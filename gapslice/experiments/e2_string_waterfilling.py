"""E2: string water-filling vs per-vehicle (uniform) split vs URLLC slice,
sweeping platoon length and the number of trailer-blocked (NLOSv) links.

Usage:  python -m gapslice.experiments.e2_string_waterfilling
Output: results/e2.json
"""
import json, numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.allocation.ceb import waterfill, uniform_split, urllc_link


def main():
    rows = []
    for beta in [0.0, 2.0]:
        for h in [0.6, 0.8, 1.0]:
            for N in [3, 5, 7, 9]:
                L = N - 1
                for nb in [0, 1, 2]:
                    if nb > L:
                        continue
                    flags = tuple([True] * nb + [False] * (L - nb))
                    g = P.GAMMA_LINK ** L
                    wf, gams = waterfill(h, beta, flags, g)
                    un = uniform_split(h, beta, flags, g)
                    ur = sum(urllc_link(h, f, eps=P.eps_link(L)) for f in flags)
                    rows.append(dict(beta=beta, h=h, N=N, blocked=nb,
                                     waterfill=None if not np.isfinite(wf) else float(wf),
                                     uniform=None if not np.isfinite(un) else float(un),
                                     urllc=float(ur),
                                     gammas=gams))
    json.dump(rows, open(paths.out("e2.json"), "w"), indent=1)
    for r in rows:
        wf, un, ur = r["waterfill"], r["uniform"], r["urllc"]
        s1 = "-" if (wf is None or un is None) else f"{100*(1-wf/un):.0f}%"
        s2 = "-" if wf is None else f"{100*(1-wf/ur):.0f}%"
        gm = "" if r["gammas"] is None else " ".join(f"{g:.4f}" for g in r["gammas"])
        print(f"b={r['beta']} h={r['h']} N={r['N']} blocked={r['blocked']}: WF={wf} UNI={un} URLLC={ur:.0f} | "
              f"WF vs UNI {s1} | WF vs URLLC {s2} | gammas {gm}")


if __name__ == "__main__":
    main()
