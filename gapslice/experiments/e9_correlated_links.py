"""E9: correlated slow channel states across the links of a platoon.

Assumption A2 of the paper models the losses of different links as
independent. This is a modeling assumption: different, frequency-hopped
PRBs and antennas tens of metres apart make a strong correlation of the
fast fading unlikely but do not guarantee independence, and the slow states
of neighbouring links can be correlated (shared obstacles, similar
shadowing). This experiment tests the slow-state part. It repeats the
end-to-end setting of E7 (gapslice.simulation.end_to_end), with the same
admitted platoons and GapSlice reservations, with an equicorrelated slow
state:

    z_l[t] = sqrt(c) * w[t] + sqrt(1 - c) * v_l[t],

where w is a common Gauss-Markov process (LOS decorrelation distance) and
v_l the link's own process (its LOS or NLOSv decorrelation distance); every
z_l stays a unit-variance process, so the per-link statistics, and hence the
reservations, are unchanged. c = 0 is the independent case of E7.

Reported per correlation c: platoon-level availability (Monte Carlo on the
stationary joint distribution), per-event risk (peak-error growth > 5 %,
Wilson interval), 1 % quantile of the bumper distance, and the measured
mean-square leader-to-tail amplification against the contracted bound.

Usage: python -m gapslice.experiments.e9_correlated_links A|B
Output: results/e9_A.json / e9_B.json
"""
import json, sys, time
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.channel import fsmc as CT
from gapslice.scenario.tenants import draw_tenants
from gapslice.allocation.market import price_only_market
from gapslice.stats import wilson
from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics
from gapslice.scenario.tenants import flags_of
from gapslice.simulation import end_to_end as E2E
from gapslice.experiments.settings import CELL_PRBS, N_TENANTS, POP_SEEDS

CORR = [0.0, 0.5, 0.9]
N_MC = 400000


def joint_traces(n, h, fl, beta, tgt, c, rng):
    """Delivery indicators (S, R, L) with equicorrelated slow states."""
    R, S = E2E.R, E2E.S_LEN
    L = len(fl)
    pcs = [E2E.p_curve(int(nl), h, bf) for nl, bf in zip(n, fl)]
    rhos = [CT.rho_of(CT.DC_NLOSV if bf else CT.DC_LOS) for bf in fl]
    rw = CT.rho_of(CT.DC_LOS)
    w = rng.standard_normal(R)
    v = rng.standard_normal((L, R))
    good = np.ones((L, R), dtype=bool)
    D = np.zeros((S, R, L), dtype=bool)
    a, b_ = np.sqrt(c), np.sqrt(1.0 - c)
    for t in range(S):
        w = rw * w + np.sqrt(1 - rw ** 2) * rng.standard_normal(R)
        for l in range(L):
            v[l] = rhos[l] * v[l] + np.sqrt(1 - rhos[l] ** 2) * rng.standard_normal(R)
            z = a * w + b_ * v[l]
            p = np.interp(z, E2E.XG, pcs[l])
            u = rng.random(R)
            if beta > 0:
                rb = np.minimum(1.0 / beta, p / np.maximum(1 - p, 1e-12))
                alpha = np.minimum(1.0, rb * (1 - p) / np.maximum(p, 1e-12))
                dl = np.where(good[l], u >= alpha, u < rb)
            else:
                dl = u < p
            good[l] = dl
            D[t, :, l] = dl
    return D


def availability(n, h, fl, tgt, c, rng):
    """Share of the stationary joint distribution in which every link meets
    its delivery target."""
    zs = []
    for nl, bf, pt in zip(n, fl, tgt):
        pc = E2E.p_curve(int(nl), h, bf)
        ok = pc >= pt - 1e-12
        if not ok.any():
            return 0.0
        i = int(np.argmax(ok))
        if i == 0:
            zs.append(-np.inf)
            continue
        z0, z1, p0, p1 = E2E.XG[i - 1], E2E.XG[i], pc[i - 1], pc[i]
        zs.append(z0 + (pt - p0) * (z1 - z0) / max(p1 - p0, 1e-15))
    w = rng.standard_normal(N_MC)
    ok = np.ones(N_MC, dtype=bool)
    for zstar in zs:
        z = np.sqrt(c) * w + np.sqrt(1 - c) * rng.standard_normal(N_MC)
        ok &= z >= zstar
    return float(ok.mean())


if __name__ == "__main__":
    CONTRACT = sys.argv[1] if len(sys.argv) > 1 else "A"
    t0 = time.time()
    rows = {c: [] for c in CORR}
    for sd in POP_SEEDS:
        T = draw_tenants(N_TENANTS, 4242 + sd, contract=CONTRACT)
        choice = price_only_market(T, CELL_PRBS, "ceb", seed=sd)
        for k, (t, ch) in enumerate(zip(T, choice)):
            h = ch[0]
            if h >= P.H_ACC - 1e-9:
                continue
            fl = flags_of(t)
            n, tgt = E2E.reservation(t.contract, h, t.beta, fl, t.eta, "GapSlice")
            for c in CORR:
                seed = 30000 * sd + 10 * k + int(10 * c)
                rng = np.random.default_rng(seed)
                u0, starts = braking_pulse(E2E.S_LEN, E2E.R, rng, 2.0, 6.0)
                D = joint_traces(n, h, fl, t.beta, tgt, c, rng)
                m = disturbance_metrics(u0, t.N, np.full(E2E.S_LEN, h), None, [t.beta] * t.L, t.eta,
                                        seed=seed + 1, deltas=D)
                ev = m["peak_growth"] > 1.05
                rows[c].append(dict(seed=sd, tenant=k, h=h, beta=t.beta, N=t.N,
                                    avail=availability(n, h, fl, tgt, c, rng),
                                    k=int(ev.sum()), n=E2E.R, dmin=m["dmin"].tolist(),
                                    ms_amp=float(np.sqrt(np.mean(m["amp"] ** 2))),
                                    gamma_contract=P.GAMMA_LINK ** t.L))
        print(f"seed {sd}: {len(rows[CORR[0]])} platoons, {time.time()-t0:.0f}s", flush=True)
    summ = {}
    for c in CORR:
        rr = rows[c]
        k = sum(r["k"] for r in rr); n = sum(r["n"] for r in rr)
        av = np.array([r["avail"] for r in rr])
        dmin = np.concatenate([np.array(r["dmin"]) for r in rr])
        summ[str(c)] = dict(platoons=len(rr), avail_mean=float(av.mean()), avail_min=float(av.min()),
                            avail_below95=int(np.sum(av < 0.95 - 1e-9)),
                            risk=k / n, ci=wilson(k, n), k=k, n=n,
                            dmin1=float(np.quantile(dmin, 0.01)),
                            ms_amp_max=float(max(r["ms_amp"] for r in rr)),
                            ms_amp_over=int(sum(1 for r in rr if r["ms_amp"] > r["gamma_contract"])))
    for c in rows:
        for r in rows[c]:
            r.pop("dmin")
    json.dump(dict(contract=CONTRACT, corr=CORR, R=E2E.R, summary=summ,
                   rows={str(c): v for c, v in rows.items()}),
              open(paths.out(f"e9_{CONTRACT}.json"), "w"), indent=1, default=float)
    for c, s in summ.items():
        print(f"c={c}: {s['platoons']} platoons, availability {100*s['avail_mean']:.2f}% (min {100*s['avail_min']:.2f}%, "
              f"{s['avail_below95']} below 95%) | risk {100*s['risk']:.2f}% [{100*s['ci'][0]:.2f},{100*s['ci'][1]:.2f}] "
              f"| dmin1 {s['dmin1']:.1f} m | ms amp max {s['ms_amp_max']:.3f} (over contract: {s['ms_amp_over']})")
    print("done", time.time() - t0)
