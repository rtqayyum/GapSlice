"""E6: a wrong burst-length estimate, and its online detection.

The reservation is planned per slow state (Eq. (12)) for a declared mean
burst length beta=2 within slow states, while the true burst length is 4.
We report the certificate over the joint modes and the per-event risk under
the true channel, and test an online check: from sidelink HARQ feedback
(assumption A1) the gNB computes the mean loss-run length of a link over a
window and raises a flag when it exceeds the 95th percentile expected under
the declared model (5 % false alarms). Protection before detection (probation): the platoon
keeps the declared-plan reservation but drives at the smallest gap at which
that reservation meets the contract for a guard burst length
2 * beta_declared; the test runs on the same reservation and keeps its power;
the gap returns to the requested one once a window passes the test.

Usage:  python -m gapslice.experiments.e6_wrong_burst_length
Output: results/e6.json
"""
import json, time
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.channel import fsmc as CT
from gapslice.descriptor.tables import p_c
from gapslice.stats import wilson
from gapslice.channel.link import mean_sinr_db, prbs_for_target, delivery_prob
from gapslice.scenario.tenants import H_OFFER
from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics

H_LIST = [0.8, 1.0, 1.2]
B_DECL, B_TRUE = 2.0, 4.0
N, R = 5, 3000
S_LEN = int(12 / P.T)
WINDOWS = {"10 s": 300, "30 s": 900}
N_WIN = 4000


def run_stat(d):
    """Mean loss-run length per window (rows) from delivery indicators."""
    lost = ~d
    n_loss = lost.sum(axis=1)
    starts = (lost[:, 1:] & ~lost[:, :-1]).sum(axis=1) + lost[:, 0]
    return np.where(starts > 0, n_loss / np.maximum(starts, 1), 0.0)


def window_stats(Pt, ps_full, beta, W, rng):
    d = CT.traces(Pt, ps_full, W, N_WIN, 1, rng, beta=beta)[:, :, 0].T   # (N_WIN, W)
    return run_stat(d)


if __name__ == "__main__":
    t0 = time.time()
    x, pi, Pt, av, xe = CT.fsmc(CT.sigma_ls(False), CT.rho_of(CT.DC_LOS))
    Q = CT.restrict(Pt, av)
    rows = []
    for h in H_LIST:
        row = dict(h=h)
        for label, b_plan in [("declared", B_DECL), ("correct", B_TRUE)]:
            pc = p_c(h, b_plan, P.GAMMA_LINK)
            tot, m, b = prbs_for_target(pc, mean_sinr_db(h, False) + xe)
            ps = CT.state_probs(h, False, m, b, x[av])
            g = CT.joint_gain(h, Q, ps, beta=B_TRUE)
            rng = np.random.default_rng(int(100 * h) + (1 if label == "declared" else 2))
            u0, _ = braking_pulse(S_LEN, R, rng, 2.0, 6.0)
            d = CT.traces(Q, ps, S_LEN, R, N - 1, rng, beta=B_TRUE)
            met = disturbance_metrics(u0, N, np.full(S_LEN, h), None, [B_TRUE] * (N - 1),
                                      seed=7, deltas=d)
            k = int(np.sum(met["peak_growth"] > 1.05))
            row[label] = dict(p_c=pc, prbs=int(tot), m=int(m), b=int(b), gain=g, k=k, n=R,
                              risk=k / R, ci=wilson(k, R),
                              dmin1=float(np.quantile(met["dmin"], 0.01)))
        # online check for the declared plan (full chain, as the gNB sees it)
        m, b = row["declared"]["m"], row["declared"]["b"]
        ps_full = CT.state_probs(h, False, m, b, x)
        rng = np.random.default_rng(99 + int(10 * h))
        det = {}
        for wname, W in WINDOWS.items():
            s0 = window_stats(Pt, ps_full, B_DECL, W, rng)
            thr = float(np.quantile(s0, 0.95))
            s1 = window_stats(Pt, ps_full, B_TRUE, W, rng)
            det[wname] = dict(threshold=thr, false_alarm=float(np.mean(s0 > thr)),
                              detection=float(np.mean(s1 > thr)))
        row["online"] = det
        # probation: until the link has passed the test once, the platoon keeps
        # the declared-plan reservation but drives at the smallest gap h_g >= h
        # at which that reservation meets the contract also for the guard
        # burst length beta_g = 2 * beta_declared (= 4 here). The test then
        # runs on the same reservation, so it keeps its power.
        h_g = None
        for hh in H_OFFER:
            if hh < h - 1e-9:
                continue
            pcg = p_c(hh, 2 * B_DECL, P.GAMMA_LINK)
            if np.isfinite(pcg) and delivery_prob(b, m, mean_sinr_db(hh, False) + xe) >= pcg:
                h_g = hh
                break
        prob = dict(h_g=h_g)
        if h_g is not None:
            ps_g = CT.state_probs(h_g, False, m, b, x[av])
            prob["gain"] = CT.joint_gain(h_g, Q, ps_g, beta=B_TRUE)
            rng = np.random.default_rng(int(100 * h) + 3)
            u0, _ = braking_pulse(S_LEN, R, rng, 2.0, 6.0)
            d = CT.traces(Q, ps_g, S_LEN, R, N - 1, rng, beta=B_TRUE)
            met = disturbance_metrics(u0, N, np.full(S_LEN, h_g), None, [B_TRUE] * (N - 1),
                                      seed=7, deltas=d)
            k = int(np.sum(met["peak_growth"] > 1.05))
            prob.update(k=k, n=R, risk=k / R, ci=wilson(k, R))
            ps_gf = CT.state_probs(h_g, False, m, b, x)
            detp = {}
            for wname, W in WINDOWS.items():
                s0 = window_stats(Pt, ps_gf, B_DECL, W, rng)
                thr = float(np.quantile(s0, 0.95))
                s1 = window_stats(Pt, ps_gf, B_TRUE, W, rng)
                detp[wname] = dict(threshold=thr, false_alarm=float(np.mean(s0 > thr)),
                                   detection=float(np.mean(s1 > thr)))
            prob["online"] = detp
        row["probation"] = prob
        rows.append(row)
        dd, cc = row["declared"], row["correct"]
        print(f"h={h}: declared plan {dd['prbs']} PRB gain={dd['gain']:.4f} risk={100*dd['risk']:.1f}% "
              f"| correct plan {cc['prbs']} PRB gain={cc['gain']:.4f} risk={100*cc['risk']:.1f}% "
              f"| detection {det['10 s']['detection']:.3f} (10 s), {det['30 s']['detection']:.3f} (30 s) "
              f"| probation gap {row['probation'].get('h_g')} gain={row['probation'].get('gain', float('nan')):.4f} "
              f"risk={100*row['probation'].get('risk', float('nan')):.1f}% "
              f"{time.time()-t0:.0f}s", flush=True)
    json.dump(dict(rows=rows, beta_declared=B_DECL, beta_true=B_TRUE), open(paths.out("e6.json"), "w"),
              indent=1, default=float)
    print("done", time.time() - t0)
