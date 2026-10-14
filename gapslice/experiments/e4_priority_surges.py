"""E4: priority surge in one cell, stability loans with a loan clause
(Algorithm 2) vs baselines.

Platoons are admitted by the price-only gap market (Algorithm 1). At t_s a
high-priority demand D = f * (reserved PRBs) arrives. Free capacity is used
first; the rest is borrowed from platoons with the loan algorithm of
:mod:`gapslice.allocation.loans`.
Baselines: wait-for-maneuver, graduated release, naive preemption, static
(lenders start at the next epoch).

Reported: service of the surge over time; the contracted metric evaluated
at the start gap of every step (frozen gap); and, by Monte Carlo, the
per-event spacing-error growth, the 99th-percentile spacing error, the 1 %
quantile of the bumper distance and the measured mean-square amplification
of each lender, with a hard brake at a random time during its maneuver.
A clause sweep (gamma_loan, delta_loan, T_loan) reports service and the
frozen-gap metric.

Usage: python -m gapslice.experiments.e4_priority_surges A|B
Output: results/e4_A.json / e4_B.json
"""
import json, time, sys
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.stats import wilson
from gapslice.scenario.tenants import draw_tenants, flags_of
from gapslice.allocation.market import price_only_market
from gapslice.allocation.reservation import p_of, per_link
from gapslice.allocation.loans import (T_S, GAMMA_LOAN_EXP, DELTA_LOAN, T_LOAN, POLICIES,
                                       bound, schedule, plan, alloc_at, frozen_metrics,
                                       service, service_metrics)
from gapslice.simulation.vectorized import disturbance_metrics
from gapslice.experiments.settings import CELL_PRBS, N_TENANTS, POP_SEEDS

B = CELL_PRBS
N_TEN = N_TENANTS
SEEDS = POP_SEEDS
FRACS = [0.2, 0.3, 0.5]
SIM_POL = ["No surge (reference)", "LTR (Alg. 2)", "Wait-for-maneuver", "Graduated", "Naive preemption"]
R_MC = 800


# ---------------------------------------------------------------- simulation
def simulate(t, pl, policy, seed):
    """Monte Carlo of one lender: hard brake at a random time of its maneuver."""
    st, phis = pl["steps"], pl.get("phis", [])
    fl = flags_of(t)
    h0 = st[0][0]
    t_end = st[-1][4] + st[-1][5] - T_S
    pre, post = 1.0, 6.0
    S = int(np.ceil((pre + t_end + post) / P.T))
    tt = np.arange(S) * P.T - pre
    h_t = np.full(S, h0)
    p_t = np.zeros((S, t.L))
    a0 = per_link(t.contract, h0, t.beta, fl, t.eta)
    aE = per_link(t.contract, st[-1][1], t.beta, fl, t.eta)
    for s in range(S):
        x = tt[s]
        if policy == "No surge (reference)" or x < 0:
            hc, al = h0, a0
        elif x >= t_end:
            hc, al = st[-1][1], aE
        else:
            j = max(i for i, s_ in enumerate(st) if s_[4] - T_S <= x + 1e-12)
            h, h2, _, _, ts, d = st[j]
            frac = (x - (ts - T_S)) / d
            hc = h + (h2 - h) * frac
            al = alloc_at(t, st, phis, policy, j, frac)
        h_t[s] = hc
        for l in range(t.L):
            p_t[s, l] = p_of(int(np.floor(al[l])), round(float(hc), 2), fl[l], P.eps_link(t.L))
    rng = np.random.default_rng(seed)
    k = int(round(1.5 / P.T))
    starts = rng.integers(int(pre / P.T), int((pre + t_end) / P.T), size=R_MC)
    u0 = np.zeros((R_MC, S))
    for r in range(R_MC):
        u0[r, starts[r]:starts[r] + k] = -3.0
        u0[r, starts[r] + k:starts[r] + 2 * k] = 1.5
    m = disturbance_metrics(u0, t.N, h_t, p_t, [t.beta] * t.L, t.eta, seed=seed + 1)
    return dict(k=int(np.sum(m["peak_growth"] > 1.05)), n=R_MC,
                ms_amp=float(np.sqrt(np.mean(m["amp"] ** 2))),
                e99=float(np.quantile(m["peak_e"], 0.99)),
                dmin1=float(np.quantile(m["dmin"], 0.01)),
                pmin=float(p_t[(tt >= 0) & (tt < t_end)].min()) if t_end > 0 else 1.0)


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    CONTRACT = sys.argv[1] if len(sys.argv) > 1 else "A"
    seeds = SEEDS if len(sys.argv) < 3 else list(range(int(sys.argv[2])))
    t0 = time.time()
    tgrid = np.arange(0, 90.0, 0.05)
    out = dict(B=B, contract=CONTRACT, n_tenants=N_TEN, seeds=seeds, fracs=FRACS,
               gamma_loan_exp=GAMMA_LOAN_EXP, delta_loan=DELTA_LOAN, t_loan=T_LOAN,
               service={}, frozen={}, sim={}, sweep={}, pops=[])
    for f in FRACS:
        out["service"][f] = {p: [] for p in POLICIES}
        out["frozen"][f] = {p: [] for p in POLICIES if p != "Static"}
    sim_rows = {p: [] for p in SIM_POL}
    sweep_cfg = ([("gamma_exp", e) for e in [5.0, 7.5, 10.0, 15.0, 20.0]] if CONTRACT == "A"
                 else [("delta", d) for d in [0.01, 0.02, 0.05, 0.10]]) + \
                [("t_loan", x) for x in [5.0, 10.0, 20.0, 1e9]]
    sweep = {f"{a}={v}": [] for a, v in sweep_cfg}
    for sd in seeds:
        T = draw_tenants(N_TEN, 4242 + sd, contract=CONTRACT)
        choice = price_only_market(T, B, "ceb", seed=sd)
        reserved = sum(c[1] for c in choice)
        free = B - reserved
        pop = dict(seed=sd, reserved=reserved, cacc=sum(1 for c in choice if c[0] < P.H_ACC))
        for f in FRACS:
            D = f * reserved
            need = max(0.0, D - free)
            steps, rounds, omega = schedule(T, choice, need)
            pop[f"lenders_{f}"] = len(steps)
            pop[f"rounds_{f}"] = rounds
            pop[f"steps_{f}"] = sum(len(s) for s in steps.values())
            for pol in POLICIES:
                ev, plans = plan(T, steps, pol)
                sc = service(ev, free, D, tgrid)
                sm = service_metrics(sc, tgrid)
                if f == 0.3:
                    sm["curve"] = sc[::4].tolist()
                if pol == "LTR (Alg. 2)":
                    sm["phis"] = [p for pl in plans.values() for p in pl["phis"]]
                    sm["loan_time"] = [pl["loan_time"] for pl in plans.values()]
                out["service"][f][pol].append(sm)
                if pol != "Static":
                    for k, pl in plans.items():
                        tk = T[k]
                        w_all, w_def, n_def = frozen_metrics(tk, pl, pol, split=True)
                        out["frozen"][f][pol].append(dict(
                            seed=sd, tenant=k, beta=tk.beta, N=tk.N,
                            metric=w_all, metric_deficit=w_def, deficit_steps=n_def,
                            steps=len(pl["steps"]),
                            contract=bound(tk, "contract"), clause=bound(tk, "loan")))
            if f == 0.3:
                # clause sweep (service and frozen metric only)
                for a, v in sweep_cfg:
                    kw = dict(gexp=GAMMA_LOAN_EXP, dloan=DELTA_LOAN, tloan=T_LOAN)
                    kw[{"gamma_exp": "gexp", "delta": "dloan", "t_loan": "tloan"}[a]] = v
                    ev, plans = plan(T, steps, "LTR (Alg. 2)", **kw)
                    sm = service_metrics(service(ev, free, D, tgrid), tgrid)
                    fz = []
                    for k, pl in plans.items():
                        tk = T[k]
                        w = frozen_metrics(tk, pl, "LTR (Alg. 2)")
                        lim = bound(tk, "loan", kw["gexp"], kw["dloan"])
                        fz.append(dict(metric=w, clause=lim, contract=bound(tk, "contract")))
                    sm["frozen"] = fz
                    sweep[f"{a}={v}"].append(sm)
                # Monte Carlo of every lender
                for pol in SIM_POL:
                    _, plans = plan(T, steps, "LTR (Alg. 2)" if pol == "No surge (reference)" else pol)
                    for k, pl in plans.items():
                        r = simulate(T[k], pl, pol, seed=1000 * sd + k)
                        r.update(seed=sd, tenant=k, beta=T[k].beta, N=T[k].N,
                                 gamma_contract=P.GAMMA_LINK ** T[k].L,
                                 gamma_clause=(P.GAMMA_UNIT ** GAMMA_LOAN_EXP) ** T[k].L)
                        sim_rows[pol].append(r)
        out["pops"].append(pop)
        s3 = out["service"][0.3]
        print(f"seed {sd}: reserved {reserved:.0f} free {free:.0f} CACC {pop['cacc']}/{N_TEN} | f=0.3 lenders "
              f"{pop['lenders_0.3']} steps {pop['steps_0.3']} clock rounds {pop['rounds_0.3']} | t95 LTR "
              f"{s3['LTR (Alg. 2)'][-1]['t95']:.2f} wait {s3['Wait-for-maneuver'][-1]['t95']:.2f} "
              f"| {time.time()-t0:.0f}s", flush=True)
    out["sim"] = sim_rows
    out["sweep"] = sweep
    # ---- summary ----
    summ = {}
    for f in FRACS:
        summ[f] = {}
        for pol in POLICIES:
            S_ = out["service"][f][pol]
            d = {m: float(np.mean([s[m] for s in S_])) for m in ["t50", "t95", "t_full", "unserved10"]}
            if pol in out["frozen"][f]:
                Fz = out["frozen"][f][pol]
                d["frozen_over_clause"] = int(sum(1 for r in Fz if r["metric"] > r["clause"] * (1 + 1e-9)))
                d["deficit_over_clause"] = int(sum(1 for r in Fz if r["deficit_steps"] > 0
                                                   and r["metric_deficit"] > r["clause"] * (1 + 1e-9)))
                d["lenders_with_deficit"] = int(sum(1 for r in Fz if r["deficit_steps"] > 0))
                d["deficit_steps"] = int(sum(r["deficit_steps"] for r in Fz))
                d["worst_deficit_rel"] = float(max([r["metric_deficit"] / r["clause"] for r in Fz
                                                    if r["deficit_steps"] > 0] or [0.0]))
                d["frozen_over_contract"] = int(sum(1 for r in Fz if r["metric"] > r["contract"] * (1 + 1e-9)))
                d["n_lenders"] = len(Fz)
            summ[f][pol] = d
    sims = {}
    for pol in SIM_POL:
        rows = sim_rows[pol]
        k = sum(r["k"] for r in rows); n = sum(r["n"] for r in rows)
        sims[pol] = dict(k=k, n=n, risk=k / max(n, 1), ci=wilson(k, n),
                         ms_amp_over_contract=int(sum(1 for r in rows if r["ms_amp"] > r["gamma_contract"])),
                         ms_amp_over_clause=int(sum(1 for r in rows if r["ms_amp"] > r["gamma_clause"])),
                         ms_amp_max=float(max(r["ms_amp"] for r in rows)) if rows else None,
                         e99_max=float(max(r["e99"] for r in rows)) if rows else None,
                         dmin1_min=float(min(r["dmin1"] for r in rows)) if rows else None)
    out["summary"] = dict(service=summ, sim=sims)
    sw = {}
    for key, rows in sweep.items():
        sw[key] = dict(t95=float(np.mean([r["t95"] for r in rows])),
                       unserved10=float(np.mean([r["unserved10"] for r in rows])),
                       worst_rel=float(max([x["metric"] / x["clause"] for r in rows for x in r["frozen"]] or [0])),
                       over_contract=int(sum(1 for r in rows for x in r["frozen"] if x["metric"] > x["contract"] * (1 + 1e-9))),
                       n=int(sum(len(r["frozen"]) for r in rows)))
    out["summary"]["sweep"] = sw
    json.dump(out, open(paths.out(f"e4_{CONTRACT}.json"), "w"), indent=1, default=float)
    for f in FRACS:
        for pol in POLICIES:
            d = summ[f][pol]
            print(f"f={f} {pol:18s} t50={d['t50']:.2f} t95={d['t95']:.2f} full={d['t_full']:.2f} "
                  f"unserved10={100*d['unserved10']:.1f}%"
                  + (f" frozen>clause {d['frozen_over_clause']}/{d['n_lenders']} >contract {d['frozen_over_contract']}"
                     if "n_lenders" in d else ""))
    for pol, s in sims.items():
        print(f"sim {pol:22s}: risk {100*s['risk']:.2f}% [{100*s['ci'][0]:.2f},{100*s['ci'][1]:.2f}] (n={s['n']}) "
              f"ms_amp max {s['ms_amp_max']:.4f} (>contract {s['ms_amp_over_contract']}) e99 max {s['e99_max']:.2f} "
              f"dmin1 min {s['dmin1_min']:.1f}")
    for key, s in sw.items():
        print(f"sweep {key:16s}: t95={s['t95']:.2f} unserved10={100*s['unserved10']:.1f}% worst metric/clause "
              f"{s['worst_rel']:.4f} over contract {s['over_contract']}/{s['n']}")
    print("done", time.time() - t0)
