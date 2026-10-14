"""E3: price-only gap market (Algorithm 1) vs baselines in one cell.

Sweeps the number of platoon tenants at a fixed slice pool B, with 100
independent tenant populations per load point. Policies:
  Oracle            exact optimum of P1 with CEB menus (MILP, full information)
  Market (CEB)      Algorithm 1 with CEB menus (price-only)
  Market (classes)  Algorithm 1 with outcome-matched reliability-class menus
  CEB-fixed         descriptor at the preferred gap, greedy admission
  99.99 %-fixed     99.99 % slice at the preferred gap, greedy admission
  Equal share       equal split of the pool
All policies meet the same contract for every admitted gap (rejected tenants
drive in ACC). Utilities are reported relative to the oracle of the same
population, with 95 % t-intervals of the mean over populations.

Usage:  python -m gapslice.experiments.e3_gap_market A|B
Output: results/e3_A.json / e3_B.json
"""
import json, time, sys
import numpy as np
from scipy.stats import t as tdist
from gapslice import params as P
from gapslice import paths
from gapslice.scenario.tenants import draw_tenants
from gapslice.allocation.market import price_only_market, oracle, greedy_fixed, equal_share, evaluate

B = 6000.0
N_LIST = [4, 8, 12, 16, 20, 24, 32, 40]
N_POP = 100
POL = ["Oracle", "Market (CEB)", "Market (classes)", "CEB-fixed", "99.99%-fixed", "Equal share"]


def ci(x):
    x = np.asarray(x, dtype=float)
    m = float(np.mean(x))
    if len(x) < 2:
        return m, m, m
    hw = float(tdist.ppf(0.975, len(x) - 1) * np.std(x, ddof=1) / np.sqrt(len(x)))
    return m, m - hw, m + hw


if __name__ == "__main__":
    CONTRACT = sys.argv[1] if len(sys.argv) > 1 else "A"
    npop = int(sys.argv[2]) if len(sys.argv) > 2 else N_POP
    t0 = time.time()
    raw = {p: {n: [] for n in N_LIST} for p in POL}
    rounds = {n: [] for n in N_LIST}
    for n in N_LIST:
        for s in range(npop):
            T = draw_tenants(n, seed=100000 + 1000 * n + s, contract=CONTRACT)
            ch_m, info = price_only_market(T, B, "ceb", seed=s, return_info=True)
            rounds[n].append(info["rounds"])
            ch = {"Oracle": oracle(T, B, "ceb"),
                  "Market (CEB)": ch_m,
                  "Market (classes)": price_only_market(T, B, "tier", seed=s),
                  "CEB-fixed": greedy_fixed(T, B, "ceb"),
                  "99.99%-fixed": greedy_fixed(T, B, "urllc"),
                  "Equal share": equal_share(T, B, "ceb")}
            for p in POL:
                raw[p][n].append(evaluate(T, ch[p], B))
            raw["Oracle"][n][-1]["offered_urllc"] = float(
                sum(t.urllc_demand(t.h_pref_urllc()) for t in T) / B)
        print(f"n={n} done {time.time()-t0:.0f}s", flush=True)
    summ = {}
    for p in POL:
        summ[p] = {}
        for n in N_LIST:
            R, O = raw[p][n], raw["Oracle"][n]
            ratio = [r["utility"] / o["utility"] for r, o in zip(R, O)]
            m, lo, hi = ci(ratio)
            summ[p][n] = dict(util_ratio=m, util_ratio_lo=lo, util_ratio_hi=hi,
                              util_ratio_min=float(np.min(ratio)),
                              cacc_frac=float(np.mean([r["cacc_frac"] for r in R])),
                              mean_gap=float(np.mean([r["mean_gap"] for r in R])),
                              util_frac=float(np.mean([r["util_frac"] for r in R])),
                              feasible=bool(all(r["feasible"] for r in R)))
    for n in N_LIST:
        summ["Oracle"][n]["offered_urllc"] = float(np.mean([r["offered_urllc"] for r in raw["Oracle"][n]]))
        summ["Market (CEB)"][n]["rounds_mean"] = float(np.mean(rounds[n]))
        summ["Market (CEB)"][n]["rounds_max"] = int(np.max(rounds[n]))
    json.dump(dict(B=B, N=N_LIST, n_pop=npop, contract=CONTRACT, summary=summ,
                   ratios={p: {n: [r["utility"] / o["utility"] for r, o in zip(raw[p][n], raw["Oracle"][n])]
                               for n in N_LIST} for p in POL}),
              open(paths.out(f"e3_{CONTRACT}.json"), "w"), indent=1)
    for p in POL:
        print(p)
        for n in N_LIST:
            s = summ[p][n]
            print(f"  n={n:2d} U/U*={s['util_ratio']:.4f} [{s['util_ratio_lo']:.4f},{s['util_ratio_hi']:.4f}] "
                  f"min {s['util_ratio_min']:.3f} CACC={100*s['cacc_frac']:.0f}% gap={s['mean_gap']:.2f}s "
                  f"used={100*s['util_frac']:.0f}% feas={s['feasible']}"
                  + (f" rounds={s['rounds_mean']:.0f} (max {s['rounds_max']})" if "rounds_mean" in s else "")
                  + (f" load(99.99%)={s['offered_urllc']:.2f}" if "offered_urllc" in s else ""))
    print("done", time.time() - t0)
