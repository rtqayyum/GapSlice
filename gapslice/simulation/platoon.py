"""Time-domain platoon simulator in physical coordinates (positions,
velocities, accelerations). Independent of the MJLS matrices, so it also
serves as a cross-check of the jump-system derivation.

Supports a time-varying gap h(t) and time-varying per-link delivery
probability p_l(t) with Gilbert bursts.
"""
import numpy as np
from gapslice import params as P
from gapslice.control.mjls import zoh_coeffs


def simulate(u0, N, h_of_t, p_of_t, beta=2.0, eta=P.ETA_DEFAULT,
             K=P.K_FALLBACK, kp=P.KP, kd=P.KD, T=P.T, rng=None,
             v0=P.V0, deltas=None):
    """u0: leader desired acceleration sequence (len S).
    h_of_t(t) -> gap used by all followers at step t.
    p_of_t(t, l) -> delivery prob of link l (1..N-1) at step t.
    deltas: optional pre-drawn delivery indicators [S, N] (overrides p).
    Returns dict with u [S,N], e [S,N], gapdist [S,N], a [S,N]."""
    rng = np.random.default_rng() if rng is None else rng
    S = len(u0)
    c1, c2, c3, c4, c5, c6 = zoh_coeffs(eta, T)
    h0 = h_of_t(0)
    q = np.zeros(N); v = np.full(N, v0); a = np.zeros(N); u = np.zeros(N)
    for i in range(1, N):  # equilibrium spacing
        q[i] = q[i - 1] - (P.TRUCK_LEN + P.R_STAND + h0 * v0)
    uhat = np.zeros(N)
    lost = np.zeros(N, dtype=int)
    good = np.ones(N, dtype=bool)  # Gilbert state: last CAM delivered?
    U = np.zeros((S, N)); E = np.zeros((S, N)); D = np.zeros((S, N)); Acc = np.zeros((S, N))
    for t in range(S):
        h = h_of_t(t)
        u[0] = u0[t]
        # measurements and errors at t
        e = np.zeros(N); edot = np.zeros(N); gap = np.zeros(N)
        for i in range(1, N):
            d = q[i - 1] - q[i] - P.TRUCK_LEN
            gap[i] = d
            e[i] = d - P.R_STAND - h * v[i]
            edot[i] = (v[i - 1] - v[i]) - h * a[i]
        U[t] = u; E[t] = e; D[t] = gap; Acc[t] = a
        # communication of u_{i-1}[t] to follower i (used at t+1)
        new_uhat = uhat.copy()
        for i in range(1, N):
            if deltas is not None:
                ok = bool(deltas[t, i])
            else:
                p = p_of_t(t, i)
                if beta is None:
                    ok = rng.random() < p
                else:
                    rho = min(1.0 / beta, p / max(1 - p, 1e-12))   # bursts lengthen below 1/(1+beta)
                    alpha = min(1.0, rho * (1 - p) / max(p, 1e-9))
                    ok = (rng.random() >= alpha) if good[i] else (rng.random() < rho)
            good[i] = ok
            if ok:
                lost[i] = 0
                new_uhat[i] = u[i - 1]
            else:
                lost[i] = min(lost[i] + 1, K)
                new_uhat[i] = 0.0 if lost[i] >= K else uhat[i]
        # controller update (Euler) for followers
        u_next = u.copy()
        for i in range(1, N):
            g = T / h
            u_next[i] = u[i] + g * (-u[i] + kp * e[i] + kd * edot[i] + uhat[i])
        # plant (exact ZOH)
        q_new = q + T * v + c1 * a + c2 * u
        v_new = v + c3 * a + c4 * u
        a_new = c5 * a + c6 * u
        q, v, a = q_new, v_new, a_new
        uhat = new_uhat
        u = u_next
    return dict(u=U, e=E, gap=D, a=Acc)
