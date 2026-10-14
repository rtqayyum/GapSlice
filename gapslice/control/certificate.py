"""DPP-parametrized SDP for the mean-square l2 gain: compiled once per
(h, eta), re-solved for each transition matrix (same LMI as
gapslice.control.mjls.ms_gain)."""
import numpy as np
import cvxpy as cp
from gapslice import params as P
from gapslice.control.mjls import mode_matrices, tpm, ms_radius


class GainSolver:
    def __init__(self, h, eta=P.ETA_DEFAULT, K=P.K_FALLBACK):
        self.A, self.B, self.C = mode_matrices(h, eta, K)
        M, n = K + 1, 6
        self.Pi = cp.Parameter((M, M), nonneg=True)
        Ps = [cp.Variable((n, n), symmetric=True) for _ in range(M)]
        g2 = cp.Variable()
        cons = []
        for j in range(M):
            E = sum(self.Pi[j, m] * Ps[m] for m in range(M))
            Aj, Bj, C = self.A[j], self.B[j], self.C
            tl = Aj.T @ E @ Aj - Ps[j] + C.T @ C
            tr = Aj.T @ E @ Bj
            br = Bj.T @ E @ Bj - g2 * np.eye(1)
            blk = cp.bmat([[tl, tr], [tr.T, br]])
            cons += [(blk + blk.T) / 2 << -1e-7 * np.eye(n + 1),
                     Ps[j] >> 1e-7 * np.eye(n)]
        self.g2 = g2
        self.prob = cp.Problem(cp.Minimize(g2), cons)
        self.K = K

    def gain_pi(self, Pi):
        if ms_radius(self.A, Pi) >= 1 - 1e-9:
            return np.inf
        self.Pi.value = Pi
        try:
            self.prob.solve(solver="CLARABEL")
        except Exception:
            return np.inf
        if self.prob.status not in ("optimal", "optimal_inaccurate") or self.g2.value is None:
            return np.inf
        return float(np.sqrt(max(self.g2.value, 0)))

    def gain(self, p, beta):
        return self.gain_pi(tpm(p, beta, self.K))
