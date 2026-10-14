"""E5: how a reservation sets both p and beta on a time-correlated channel,
and which planning rule meets the contract (type A, declared independent
losses within a slow state). One link of a 5-truck platoon: per-link
outage share eps_l = eps/4 (platoon-level availability 95 %).

Planning rules for one V2V link at gap h:
  * 99.99 % slice : 99.99 % delivery at the eps-quantile of the large-scale SINR
  * time average  : time-averaged delivery pbar >= p_c(beta_bar), where
                    beta_bar is the time-averaged mean loss-run length
  * per state     : Eq. (12), p_s >= p_c(h) in every available slow state
                    (equivalently at the eps-quantile)
Each plan is checked with the certificate over the joint (slow state, loss
counter) modes of the available states, and with per-event simulation of a
5-truck platoon on explicit delivery traces.

Usage:  python -m gapslice.experiments.e5_time_correlated_channel
Output: results/e5.json
"""
import json, time
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.channel import fsmc as CT
from gapslice.descriptor.tables import p_c, p_c_runlength
from gapslice.stats import wilson
from gapslice.channel.link import mean_sinr_db, prbs_for_target, delivery_prob
from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics

H_LIST = [0.6, 0.8, 1.0, 1.2]
CASES = [("LOS", False, CT.DC_LOS), ("LOS", False, 25.0), ("LOS", False, 50.0),
         ("NLOSv", True, CT.DC_NLOSV), ("NLOSv", True, 25.0), ("NLOSv", True, 50.0)]
GAMMA = P.GAMMA_LINK
N, R = 5, 3000
S_LEN = int(12 / P.T)


def chain(blocked, dc):
    x, pi, Pt, av, xe = CT.fsmc(CT.sigma_ls(blocked), CT.rho_of(dc))
    return x, Pt, av, xe


def plan_per_state(h, blocked, xe, p_target):
    tot, m, b = prbs_for_target(p_target, mean_sinr_db(h, blocked) + xe)
    return int(tot), int(m), int(b)


def plan_time_average(h, blocked, x, Q, av):
    best = (np.inf, 0, 0)
    for m in range(1, P.M_MAX + 1):
        for b in range(int(np.ceil(P.PAYLOAD_BITS / (P.SE_MAX * P.N_RE_PRB))), 400):
            if m * b >= best[0]:
                break
            ps = CT.state_probs(h, blocked, m, b, x[av])
            pb, rb = CT.loss_stats(Q, ps)
            pc = p_c_runlength(h, rb, GAMMA)
            if np.isfinite(pc) and pb >= pc:
                best = (m * b, m, b)
                break
    return best


def evaluate(h, blocked, x, Q, av, m, b, seed):
    ps = CT.state_probs(h, blocked, m, b, x[av])
    pb, rb = CT.loss_stats(Q, ps)
    g = CT.joint_gain(h, Q, ps)
    rng = np.random.default_rng(seed)
    u0, _ = braking_pulse(S_LEN, R, rng, 2.0, 6.0)
    d = CT.traces(Q, ps, S_LEN, R, N - 1, rng)
    met = disturbance_metrics(u0, N, np.full(S_LEN, h), None, [0.0] * (N - 1), seed=seed + 1, deltas=d)
    k = int(np.sum(met["peak_growth"] > 1.05))
    return dict(m=m, b=b, prbs=m * b, pbar=pb, beta_bar=rb, p_min=float(ps.min()),
                gain=g, k=k, n=R, risk=k / R, ci=wilson(k, R),
                e99=float(np.quantile(met["peak_e"], 0.99)),
                dmin1=float(np.quantile(met["dmin"], 0.01)))


def curves():
    """Panels (a)-(b) of the channel figure: pbar and beta_bar vs PRBs for
    m = 1, 2, 4 attempts."""
    h, blocked, dc = 1.0, False, CT.DC_LOS
    x, Pt, av, xe = chain(blocked, dc)
    Q = CT.restrict(Pt, av)
    out = {}
    for m in [1, 2, 4]:
        rows = []
        for b in range(12, 260, 4):
            ps = CT.state_probs(h, blocked, m, b, x[av])
            pb, rb = CT.loss_stats(Q, ps)
            rows.append((m * b, pb, rb))
            if pb > 1 - 1e-6:
                break
        out[m] = rows
    return out


if __name__ == "__main__":
    t0 = time.time()
    res = []
    for (name, blocked, dc) in CASES:
        x, Pt, av, xe = chain(blocked, dc)
        Q = CT.restrict(Pt, av)
        for h in H_LIST:
            pc = p_c(h, 0.0, GAMMA)
            row = dict(link=name, blocked=blocked, dc=dc, h=h, p_c=pc, x_eps=xe)
            for rule in ["slice", "time_avg", "per_state"]:
                if rule == "slice":
                    tot, m, b = plan_per_state(h, blocked, xe, P.P_URLLC)
                elif rule == "per_state":
                    tot, m, b = plan_per_state(h, blocked, xe, pc)
                else:
                    tot, m, b = plan_time_average(h, blocked, x, Q, av)
                if not np.isfinite(tot) or m == 0:
                    row[rule] = None
                    continue
                row[rule] = evaluate(h, blocked, x, Q, av, m, b, seed=int(1000 * h + dc))
            res.append(row)
            msg = " | ".join(f"{r}: {row[r]['prbs']} PRB g={row[r]['gain']:.4f} risk={100*row[r]['risk']:.2f}% "
                             f"(pbar={row[r]['pbar']:.4f}, beta={row[r]['beta_bar']:.2f})"
                             for r in ["slice", "time_avg", "per_state"] if row[r])
            print(f"{name} dc={dc} h={h}: {msg}  {time.time()-t0:.0f}s", flush=True)
    out = dict(rows=res, curves=curves(), gamma=GAMMA, eps_link=P.EPS_LINK_REF, eps_platoon=P.EPS_LS)
    json.dump(out, open(paths.out("e5.json"), "w"), indent=1, default=float)
    print("done", time.time() - t0)
