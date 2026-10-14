"""E7: end-to-end validation, from admission to braking.

Tenants are admitted by the price-only market (Algorithm 1, 20 tenants per
cell, the 10 populations of E4). Every platoon admitted to a CACC gap is then
simulated with its per-link reservation on the continuous time-correlated
channel of :mod:`gapslice.simulation.end_to_end`, under three reservation
rules (GapSlice, per-link eps, 99.99 % slice).

Reported per rule: PRBs, measured share of time in which every link of the
platoon meets its descriptor (platoon-level availability), per-event risk
(peak-error growth > 5 %, Wilson interval) overall and split by whether all
links met their descriptors at the onset of the brake, 1 % quantile of the bumper
distance, and the measured mean-square leader-to-tail amplification.

Usage: python -m gapslice.experiments.e7_end_to_end A|B
Output: results/e7_A.json / e7_B.json
"""
import json, sys, time
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.stats import wilson
from gapslice.scenario.tenants import draw_tenants
from gapslice.allocation.market import price_only_market
from gapslice.simulation.end_to_end import R, RULES, simulate
from gapslice.experiments.settings import CELL_PRBS, N_TENANTS, POP_SEEDS

B = CELL_PRBS
N_TEN = N_TENANTS
SEEDS = POP_SEEDS


if __name__ == "__main__":
    CONTRACT = sys.argv[1] if len(sys.argv) > 1 else "A"
    seeds = SEEDS if len(sys.argv) < 3 else list(range(int(sys.argv[2])))
    t0 = time.time()
    rows = {r: [] for r in RULES}
    for sd in seeds:
        T = draw_tenants(N_TEN, 4242 + sd, contract=CONTRACT)
        choice = price_only_market(T, B, "ceb", seed=sd)
        for k, (t, c) in enumerate(zip(T, choice)):
            h = c[0]
            if h >= P.H_ACC - 1e-9:
                continue
            for rule in RULES:
                r = simulate(t, h, rule, seed=10000 * sd + 10 * k)
                r.update(seed=sd, tenant=k, h=h, beta=t.beta, N=t.N, blocked=t.nb)
                rows[rule].append(r)
        print(f"seed {sd}: {len(rows['GapSlice'])} platoons so far, {time.time()-t0:.0f}s", flush=True)
    summ = {}
    for rule in RULES:
        rr = rows[rule]
        k = sum(r["k"] for r in rr); n = sum(r["n"] for r in rr)
        ka = sum(r["k_av"] for r in rr); na = sum(r["n_av"] for r in rr)
        ko = sum(r["k_out"] for r in rr); no = sum(r["n_out"] for r in rr)
        av = np.array([r["avail"] for r in rr])
        ax = np.array([r["avail_exact"] for r in rr])
        dmin = np.concatenate([np.array(r["dmin"]) for r in rr])
        summ[rule] = dict(platoons=len(rr), prbs=int(sum(r["prbs"] for r in rr)),
                          avail_mean=float(av.mean()), avail_min=float(av.min()),
                          avail_exact_mean=float(ax.mean()), avail_exact_min=float(ax.min()),
                          avail_exact_below95=int(np.sum(ax < 0.95 - 1e-9)),
                          risk=k / n, ci=wilson(k, n), k=k, n=n,
                          risk_avail=ka / max(na, 1), ci_avail=wilson(ka, na), n_avail=na,
                          risk_out=ko / max(no, 1), ci_out=wilson(ko, no), n_out=no,
                          dmin1=float(np.quantile(dmin, 0.01)),
                          ms_amp_max=float(max(r["ms_amp"] for r in rr)),
                          ms_amp_over=int(sum(1 for r in rr if r["ms_amp"] > r["gamma_contract"])))
    for rule in rows:
        for r in rows[rule]:
            r.pop("dmin")
    json.dump(dict(contract=CONTRACT, seeds=seeds, R=R, summary=summ, rows=rows),
              open(paths.out(f"e7_{CONTRACT}.json"), "w"), indent=1, default=float)
    for rule, s in summ.items():
        print(f"{rule:14s}: {s['platoons']} platoons, PRB {s['prbs']}, availability simulated {100*s['avail_mean']:.2f}% "
              f"exact {100*s['avail_exact_mean']:.2f}% (min {100*s['avail_exact_min']:.2f}%, {s['avail_exact_below95']} below 95%) "
              f"| risk {100*s['risk']:.2f}% "
              f"[{100*s['ci'][0]:.2f},{100*s['ci'][1]:.2f}] | onset available {100*s['risk_avail']:.2f}% (n={s['n_avail']}) "
              f"| onset in outage {100*s['risk_out']:.2f}% (n={s['n_out']}) | dmin1 {s['dmin1']:.1f} m | ms amp max {s['ms_amp_max']:.3f}")
    print("done", time.time() - t0)
