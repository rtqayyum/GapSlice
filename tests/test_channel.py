"""Checks of the time-correlated channel model (gapslice.channel.fsmc):
  1. on a one-state chain, the certificate over joint modes equals the
     Gilbert certificate of Eq. (7);
  2. the analytic time-averaged delivery probability and mean loss-run
     length of a reservation agree with long simulated delivery traces."""
import numpy as np
from gapslice.channel import fsmc as CT
from gapslice.control.certificate import GainSolver


def test_joint_certificate_reduces_to_gilbert():
    for h, p, beta in [(0.8, 0.9, 2.0), (1.0, 0.8, 0.0), (0.6, 0.95, 4.0)]:
        g_joint = CT.joint_gain(h, np.ones((1, 1)), np.array([p]), beta=beta)
        g_gil = GainSolver(h).gain(p, None if beta == 0 else beta)
        print(f"h={h} p={p} beta={beta}: joint {g_joint:.8f}  Gilbert {g_gil:.8f}")
        assert abs(g_joint - g_gil) < 1e-5


def test_loss_statistics_match_traces():
    x, pi, Pt, av, xe = CT.fsmc(CT.sigma_ls(False), CT.rho_of(CT.DC_LOS))
    Q = CT.restrict(Pt, av)
    rng = np.random.default_rng(5)
    for m, b, beta in [(1, 40, 0.0), (2, 30, 0.0), (1, 60, 2.0)]:
        ps = CT.state_probs(1.0, False, m, b, x[av])
        pb, rb = CT.loss_stats(Q, ps, beta)
        d = CT.traces(Q, ps, 20000, 50, 1, rng, beta=beta)[:, :, 0]
        lost = ~d
        starts = (lost[1:] & ~lost[:-1]).sum() + lost[0].sum()
        pb_s, rb_s = d.mean(), lost.sum() / max(starts, 1)
        print(f"m={m} b={b} beta={beta}: pbar {pb:.4f} vs {pb_s:.4f}; run length {rb:.3f} vs {rb_s:.3f}")
        assert abs(pb - pb_s) < 3e-3 and abs(rb - rb_s) / rb < 0.03


if __name__ == "__main__":
    test_joint_certificate_reduces_to_gilbert()
    test_loss_statistics_match_traces()
    print("channel checks passed")
