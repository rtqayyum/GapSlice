"""E8: comparison with three published methods (adapted implementations).

The methods (Yan-Harri, Zhang, Lu) are implemented in
:mod:`gapslice.baselines`, each in an original and a matched mode. GapSlice
(Algorithm 1 with CEB menus) and the full-information optimum of P1 are the
reference.

For each policy we report the delivered utility (a platoon whose contract
fails at its granted gap is counted at the ACC utility), the share of
platoons in CACC, the PRBs used, the platoon-level availability and whether
the contract is met, and, by Monte Carlo on the continuous channel of E7,
the per-event risk and the bumper distance.

Usage: python -m gapslice.experiments.e8_published_methods A|B
Output: results/e8_A.json / e8_B.json
"""
import json, sys, time
import numpy as np
from scipy.stats import t as tdist
from gapslice import params as P
from gapslice import paths
from gapslice.stats import wilson
from gapslice.scenario.tenants import draw_tenants, Tenant, flags_of
from gapslice.allocation.ceb import urllc_link
from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics
from gapslice.simulation import end_to_end as E2E
from gapslice.evaluation.contract import availability, design_ok, eps_of
from gapslice.baselines import METHODS, INFO, allocate
from gapslice.baselines.common import gs_links
from gapslice.baselines import yan_harri, lu
from gapslice.experiments.settings import CELL_PRBS

B = CELL_PRBS
N_LIST = [10, 20, 30, 40]
N_POP = 100
SIM_LOAD, SIM_POPS, R_SIM = 20, 20, 400


# ---------------------------------------------------------------- evaluation
def evaluate(T, alloc):
    rows = []
    for t, (h, n) in zip(T, alloc):
        if h >= P.H_ACC - 1e-9:
            rows.append(dict(cacc=False, ok=True, avail=None, U=t.U(P.H_ACC), prbs=0))
            continue
        av = availability(t, h, n)
        ok = av >= 1 - P.EPS_LS
        rows.append(dict(cacc=True, ok=bool(ok), avail=av, design_ok=design_ok(t, h, n),
                         U=t.U(h) if ok else t.U(P.H_ACC), U_nominal=t.U(h), prbs=int(sum(n))))
    return rows


def simulate(t, h, n, seed):
    rng = np.random.default_rng(seed)
    u0, _ = braking_pulse(E2E.S_LEN, R_SIM, rng, 2.0, 6.0)
    D = np.zeros((E2E.S_LEN, R_SIM, t.L), dtype=bool)
    for l, (nl, bf) in enumerate(zip(n, flags_of(t))):
        d, _ = E2E.link_trace(int(nl), round(h, 2), bf, t.beta, 0.0, rng, runs=R_SIM)
        D[:, :, l] = d
    m = disturbance_metrics(u0, t.N, np.full(E2E.S_LEN, h), None, [t.beta] * t.L, t.eta,
                            seed=seed + 1, deltas=D)
    return int(np.sum(m["peak_growth"] > 1.05)), m["dmin"]


def ci(x):
    x = np.asarray(x, dtype=float)
    m = float(np.mean(x))
    hw = float(tdist.ppf(0.975, len(x) - 1) * np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0
    return m, m - hw, m + hw


def per_link_table(contract, n_plat=300, H=(0.6, 1.0, 1.5)):
    """Per-link PRBs of a five-truck platoon at fixed gaps, matched modes."""
    rng = np.random.default_rng(77)
    plats = []
    while len(plats) < n_plat:
        eta = float(rng.choice([0.3, 0.4]))
        beta = float(rng.choice([0.0, 2.0, 4.0], p=[0.3, 0.5, 0.2]))
        blocked = rng.random(4) < 0.2
        plats.append(Tenant(len(plats), 5, eta, beta, blocked, 1.0, contract))
    out = {}
    for h in H:
        rows = {m: [] for m in ["GapSlice", "Yan-Harri (matched)", "Zhang (matched)", "Lu (matched)", "99.99% slice"]}
        infeasible = 0
        for t in plats:
            g = gs_links(t, h)
            if g is None or sum(g) <= 0:
                infeasible += 1
                continue
            ys = yan_harri.slot_matched(t, h)
            lm = lu.links_matched(t, h)
            if ys is None or lm is None:
                infeasible += 1
                continue
            base = sum(g)
            ur = sum(int(urllc_link(h, bf, eps=eps_of(t))) for bf in flags_of(t))
            for m, v in [("GapSlice", base), ("Yan-Harri (matched)", ys * t.L), ("Zhang (matched)", base),
                         ("Lu (matched)", sum(lm)), ("99.99% slice", ur)]:
                rows[m].append(v / base)
        out[str(h)] = dict(infeasible=infeasible, n=n_plat - infeasible,
                           **{m: dict(zip(["mean", "lo", "hi"], ci(v))) if v else None for m, v in rows.items()})
    return out


if __name__ == "__main__":
    CONTRACT = sys.argv[1] if len(sys.argv) > 1 else "A"
    npop = int(sys.argv[2]) if len(sys.argv) > 2 else N_POP
    t0 = time.time()
    res = {m: {n: [] for n in N_LIST} for m in METHODS}
    sim = {m: dict(k=0, n=0, dmin=[]) for m in METHODS}
    for n in N_LIST:
        for s in range(npop):
            T = draw_tenants(n, seed=500000 + 1000 * n + s, contract=CONTRACT)
            evals = {}
            for m in METHODS:
                al = allocate(T, m, seed=s, B=B)
                ev = evaluate(T, al)
                evals[m] = ev
                cacc = [r for r in ev if r["cacc"]]
                res[m][n].append(dict(
                    U=float(sum(r["U"] for r in ev)),
                    U_nominal=float(sum(r.get("U_nominal", r["U"]) for r in ev)),
                    prbs=float(sum(r["prbs"] for r in ev)) / B,
                    cacc_granted=len(cacc) / n,
                    cacc_delivered=sum(1 for r in cacc if r["ok"]) / n,
                    met=(sum(1 for r in cacc if r["ok"]) / len(cacc)) if cacc else None,
                    design_met=(sum(1 for r in cacc if r["design_ok"]) / len(cacc)) if cacc else None,
                    avail=[r["avail"] for r in cacc]))
                if n == SIM_LOAD and s < SIM_POPS:
                    for k, (t, (h, nl)) in enumerate(zip(T, al)):
                        if h >= P.H_ACC - 1e-9:
                            continue
                        kk, dm = simulate(t, h, nl, seed=90000 + 100 * s + k)
                        sim[m]["k"] += kk; sim[m]["n"] += R_SIM; sim[m]["dmin"].append(dm)
        print(f"n={n} done {time.time()-t0:.0f}s", flush=True)
    summ = {}
    for m in METHODS:
        summ[m] = {}
        for n in N_LIST:
            R_, O = res[m][n], res["Oracle"][n]
            ratio = [r["U"] / o["U"] for r, o in zip(R_, O)]
            mu, lo, hi = ci(ratio)
            av = [a for r in R_ for a in r["avail"]]
            met = [r["met"] for r in R_ if r["met"] is not None]
            summ[m][n] = dict(util=mu, util_lo=lo, util_hi=hi, util_min=float(min(ratio)),
                              util_nominal=float(np.mean([r["U_nominal"] / o["U"] for r, o in zip(R_, O)])),
                              prbs=float(np.mean([r["prbs"] for r in R_])),
                              cacc_granted=float(np.mean([r["cacc_granted"] for r in R_])),
                              cacc_delivered=float(np.mean([r["cacc_delivered"] for r in R_])),
                              met=float(np.mean(met)) if met else None,
                              design_met=float(np.mean([r["design_met"] for r in R_ if r["design_met"] is not None]))
                              if any(r["design_met"] is not None for r in R_) else None,
                              avail_mean=float(np.mean(av)) if av else None,
                              avail_min=float(np.min(av)) if av else None,
                              avail_q05=float(np.quantile(av, 0.05)) if av else None)
        s_ = sim[m]
        dm = np.concatenate(s_["dmin"]) if s_["dmin"] else np.array([np.nan])
        summ[m]["sim"] = dict(k=s_["k"], n=s_["n"], risk=s_["k"] / max(s_["n"], 1),
                              ci=wilson(s_["k"], s_["n"]), dmin1=float(np.nanquantile(dm, 0.01)))
    out = dict(B=B, N=N_LIST, n_pop=npop, contract=CONTRACT, methods=METHODS, info=INFO,
               sim_load=SIM_LOAD, sim_pops=SIM_POPS, R_sim=R_SIM, summary=summ,
               per_link=per_link_table(CONTRACT))
    json.dump(out, open(paths.out(f"e8_{CONTRACT}.json"), "w"), indent=1, default=float)
    for m in METHODS:
        s20 = summ[m][SIM_LOAD]
        print(f"{m:22s} " + " ".join(f"n={n}:{summ[m][n]['util']:.3f}" for n in N_LIST)
              + f" | n=20 PRB {100*s20['prbs']:.0f}% CACC {100*s20['cacc_delivered']:.0f}%/{100*s20['cacc_granted']:.0f}% "
              f"met {s20['met']} avail {s20['avail_mean']} (min {s20['avail_min']}) "
              f"| risk {100*summ[m]['sim']['risk']:.2f}% d1 {summ[m]['sim']['dmin1']:.1f}")
    for h, d in out["per_link"].items():
        print(h, {m: (round(v['mean'], 2) if isinstance(v, dict) else v) for m, v in d.items()})
    print("done", time.time() - t0)
