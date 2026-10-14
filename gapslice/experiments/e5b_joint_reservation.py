"""E5 (supplement): how conservative is per-state planning?

For the LOS link (d_c = 10 m) and i.i.d. fast losses, find the smallest
reservation (m attempts x b PRBs) whose certificate over the joint
(slow state, loss counter) modes meets the per-vehicle contract, by
bisection on b for every m (the joint gain decreases as b grows), and
compare it with the per-state rule of Eq. (12).

Usage:  python -m gapslice.experiments.e5b_joint_reservation
Output: results/e5_joint.json
"""
import json, time
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.channel import fsmc as CT
from gapslice.descriptor.tables import p_c
from gapslice.channel.link import mean_sinr_db, prbs_for_target

H_LIST = [0.6, 0.8, 1.0, 1.2]


if __name__ == "__main__":
    t0 = time.time()
    x, pi, Pt, av, xe = CT.fsmc(CT.sigma_ls(False), CT.rho_of(CT.DC_LOS))
    Q = CT.restrict(Pt, av)
    rows = []
    for h in H_LIST:
        pc = p_c(h, 0.0, P.GAMMA_LINK)
        tot_ps, m_ps, b_ps = prbs_for_target(pc, mean_sinr_db(h) + xe)

        def g(m, b):
            return CT.joint_gain(h, Q, CT.state_probs(h, False, m, b, x[av]))

        best = (int(tot_ps), int(m_ps), int(b_ps), g(m_ps, b_ps))
        b_min = int(np.ceil(P.PAYLOAD_BITS / (P.SE_MAX * P.N_RE_PRB)))
        for m in range(1, P.M_MAX + 1):
            hi = int(np.ceil(best[0] / m))          # cannot beat the incumbent above this
            lo = b_min - 1
            if hi <= lo:
                continue
            ghi = g(m, hi)
            if ghi > P.GAMMA_LINK:
                continue
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if g(m, mid) <= P.GAMMA_LINK:
                    hi = mid
                else:
                    lo = mid
            if m * hi < best[0]:
                best = (m * hi, m, hi, g(m, hi))
        pb, rb = CT.loss_stats(Q, CT.state_probs(h, False, best[1], best[2], x[av]))
        rows.append(dict(h=h, per_state=dict(prbs=int(tot_ps), m=int(m_ps), b=int(b_ps)),
                         joint=dict(prbs=best[0], m=best[1], b=best[2], gain=best[3], pbar=pb, beta_bar=rb)))
        print(f"h={h}: per-state {tot_ps} PRB (m={m_ps}) | joint-optimal {best[0]} PRB (m={best[1]}, "
              f"gain {best[3]:.4f}, pbar {pb:.4f}) {time.time()-t0:.0f}s", flush=True)
    json.dump(dict(rows=rows), open(paths.out("e5_joint.json"), "w"), indent=1, default=float)
    print("done", time.time() - t0)
