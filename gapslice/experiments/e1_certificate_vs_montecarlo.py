"""E1: descriptor validation.
(A) certificate vs Monte Carlo mean-square gain;
(B) per-run tail risk of string amplification vs delivery probability;
(C) burst-agnostic reliability SLA (p tuned for i.i.d.) under real bursts.

Usage:  python -m gapslice.experiments.e1_certificate_vs_montecarlo
Output: results/e1.json
"""
import json, time, numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.descriptor.tables import p_c, load_curves
from gapslice.control.certificate import GainSolver
from gapslice.control.montecarlo import mc_gain
from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics

N = 5
S = int(12 / P.T)
R = 3000
GH2T = P.GAMMA_H2T
BN = {0.0: "iid", 2.0: "burst2", 4.0: "burst4"}


def tail(h, p, beta, eta=P.ETA_DEFAULT, seed=0):
    rng = np.random.default_rng(seed)
    u0, _ = braking_pulse(S, R, rng, 2.0, 6.0)
    m = disturbance_metrics(u0, N, np.full(S, h), np.full((S, N - 1), p),
                            [beta] * (N - 1), eta, seed=seed + 1)
    return dict(viol=float(np.mean(m["amp"] > GH2T)),
                amp99=float(np.quantile(m["amp"], 0.99)),
                amp_mean=float(np.mean(m["amp"])),
                growth_viol=float(np.mean(m["peak_growth"] > 1.0)),
                growth_viol105=float(np.mean(m["peak_growth"] > 1.05)),
                k105=int(np.sum(m["peak_growth"] > 1.05)), n=int(R),
                peak_e99=float(np.quantile(m["peak_e"], 0.99)),
                dmin1=float(np.quantile(m["dmin"], 0.01)))


if __name__ == "__main__":
    t0 = time.time()
    out = {}
    # (A) certificate vs MC (beta=2, h=0.8)
    A = []
    s = GainSolver(0.8, P.ETA_DEFAULT)
    for p in [0.5, 0.7, 0.8, 0.9, 0.95, 0.99]:
        A.append(dict(p=p, lmi=s.gain(p, 2.0),
                      mc_stat=mc_gain(0.8, p, 2.0, S=400, R=1500),
                      mc_worst=mc_gain(0.8, p, 2.0, S=400, R=1500, init=P.K_FALLBACK)))
    out["A"] = A
    print("A done", time.time() - t0, flush=True)
    # (B) tail risk sweep
    PG = [0.0, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 0.9999]
    Bres = []
    for h in [0.6, 1.0]:
        for b in [0.0, 2.0, 4.0]:
            for p in PG:
                if b > 0 and p < 1 / (1 + b):
                    continue
                r = tail(h, p, b, seed=int(1000 * h + 10 * b + 1e4 * p) % 100000)
                r.update(h=h, beta=BN[b], p=p)
                Bres.append(r)
            pc = p_c(h, b, P.GAMMA_LINK)
            if np.isfinite(pc):
                r = tail(h, pc, b, seed=7); r.update(h=h, beta=BN[b], p=pc, tag="p_c")
                Bres.append(r)
            print(f"B h={h} beta={b} {time.time()-t0:.0f}s", flush=True)
    out["B"] = Bres
    # (C) burst-agnostic SLA
    C = []
    for h in [0.6, 0.8, 1.0, 1.2]:
        p_iid = p_c(h, 0.0, P.GAMMA_LINK)
        for b in [2.0, 4.0]:
            sv = GainSolver(h, P.ETA_DEFAULT)
            g_cert = sv.gain(p_iid, b) if p_iid >= 1 / (1 + b) else np.inf
            pc_true = p_c(h, b, P.GAMMA_LINK)
            r_iid = tail(h, p_iid, b, seed=11)
            r_true = tail(h, pc_true, b, seed=11) if np.isfinite(pc_true) else None
            C.append(dict(h=h, beta=BN[b], p_iid=p_iid, gamma_cert_at_p_iid=g_cert,
                          p_c_true=None if not np.isfinite(pc_true) else pc_true,
                          tail_at_p_iid=r_iid, tail_at_pc_true=r_true))
    out["C"] = C
    json.dump(out, open(paths.out("e1.json"), "w"), indent=1, default=float)
    print("done", time.time() - t0)
    for a in A:
        print(f"p={a['p']}: LMI {a['lmi']:.4f}  MC(stationary) {a['mc_stat']:.4f}  MC(worst init) {a['mc_worst']:.4f}")
    for r in Bres:
        print(f"h={r['h']} {r['beta']:7s} p={r['p']:.4f}{' (p_c)' if r.get('tag') else ''}: "
              f"P(amp>{GH2T:.3f})={100*r['viol']:.2f}%  amp99={r['amp99']:.3f}  "
              f"growth>1: {100*r['growth_viol']:.1f}%  e99={r['peak_e99']:.2f} m  dmin(1%)={r['dmin1']:.1f} m")
    for c in C:
        print(f"h={c['h']} {c['beta']}: p_iid={c['p_iid']:.4f} cert gain={c['gamma_cert_at_p_iid']:.4f} "
              f"p_c(true)={c['p_c_true']}  viol@p_iid={100*c['tail_at_p_iid']['viol']:.2f}% "
              f"viol@p_c={'-' if c['tail_at_pc_true'] is None else round(100*c['tail_at_pc_true']['viol'],2)}%")
