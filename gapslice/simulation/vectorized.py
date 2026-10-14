"""Vectorized (over Monte Carlo runs) platoon simulator in physical
coordinates, with time-varying gap h(t) and per-link delivery probability
p_l(t) under Gilbert bursts. Each configuration is simulated twice with the
same channel randomness, with and without the leader disturbance, so the
difference is exactly the disturbance response (linearity given h(t) and
the mode path)."""
import numpy as np
from gapslice import params as P
from gapslice.control.mjls import zoh_coeffs


def braking_pulse(S, R, rng, t_lo, t_hi, amp=-3.0, dur=1.5, T=P.T):
    u0 = np.zeros((R, S))
    k = int(round(dur / T))
    starts = rng.integers(int(t_lo / T), int(t_hi / T), size=R)
    for r in range(R):
        u0[r, starts[r]:starts[r] + k] = amp
        u0[r, starts[r] + k:starts[r] + 2 * k] = -amp / 2   # recover speed
    return u0, starts


def run(u0, N, h_t, p_t, betas, eta=P.ETA_DEFAULT, K=P.K_FALLBACK,
        kp=P.KP, kd=P.KD, T=P.T, v0=P.V0, rng=None, rand=None, deltas=None):
    """u0: (R,S) leader input. h_t: (S,) gap. p_t: (S,N-1) per-link delivery
    prob. betas: list of N-1 burst lengths (0 = i.i.d.).
    Returns dict of arrays: u (S,R,N), e (S,R,N), gap (S,R,N)."""
    R, S = u0.shape
    rng = np.random.default_rng() if rng is None else rng
    if rand is None and deltas is None:
        rand = rng.random((S, R, N - 1))
    c1, c2, c3, c4, c5, c6 = zoh_coeffs(eta, T)
    q = np.zeros((R, N)); v = np.full((R, N), v0); a = np.zeros((R, N))
    u = np.zeros((R, N)); uhat = np.zeros((R, N))
    lost = np.zeros((R, N), dtype=int); good = np.ones((R, N), dtype=bool)
    for i in range(1, N):
        q[:, i] = q[:, i - 1] - (P.TRUCK_LEN + P.R_STAND + h_t[0] * v0)
    betas = np.asarray(betas, dtype=float)
    U = np.zeros((S, R, N)); E = np.zeros((S, R, N)); G = np.zeros((S, R, N))
    for t in range(S):
        h = h_t[t]
        u[:, 0] = u0[:, t]
        d = q[:, :-1] - q[:, 1:] - P.TRUCK_LEN               # (R,N-1)
        e = d - P.R_STAND - h * v[:, 1:]
        edot = (v[:, :-1] - v[:, 1:]) - h * a[:, 1:]
        U[t] = u; E[t, :, 1:] = e; G[t, :, 1:] = d
        if deltas is not None:                               # explicit trace
            ok = deltas[t].astype(bool)
        else:
            # channel: Gilbert with mean burst beta (0 -> iid)
            p = p_t[t]                                       # (N-1,)
            # below p = 1/(1+beta) a Gilbert channel with mean burst beta does
            # not exist; the bursts then lengthen to (1-p)/p (alpha = 1)
            rho = np.where(betas > 0, np.minimum(1.0 / np.maximum(betas, 1e-9),
                                                 p / np.maximum(1 - p, 1e-12)), p)
            alpha = np.where(betas > 0, np.minimum(1.0, rho * (1 - p) / np.maximum(p, 1e-9)), 1 - p)
            x = rand[t]
            ok = np.where(good[:, 1:], x >= alpha, x < rho)
        good[:, 1:] = ok
        lost[:, 1:] = np.where(ok, 0, np.minimum(lost[:, 1:] + 1, K))
        new_uhat = uhat.copy()
        held = np.where(lost[:, 1:] >= K, 0.0, uhat[:, 1:])
        new_uhat[:, 1:] = np.where(ok, u[:, :-1], held)
        g = T / h
        u_next = u.copy()
        u_next[:, 1:] = u[:, 1:] + g * (-u[:, 1:] + kp * e + kd * edot + uhat[:, 1:])
        q, v, a = q + T * v + c1 * a + c2 * u, v + c3 * a + c4 * u, c5 * a + c6 * u
        uhat, u = new_uhat, u_next
    return dict(u=U, e=E, gap=G)


def disturbance_metrics(u0, N, h_t, p_t, betas, eta=P.ETA_DEFAULT, seed=0, deltas=None):
    """Simulate with/without disturbance (same channel draws) and return
    per-run head-to-tail energy amplification, peak spacing-error growth,
    and minimum bumper-to-bumper distance."""
    rng = np.random.default_rng(seed)
    R, S = u0.shape
    rand = None if deltas is not None else rng.random((S, R, N - 1))
    w = run(u0, N, h_t, p_t, betas, eta, rand=rand, deltas=deltas)
    z = run(np.zeros_like(u0), N, h_t, p_t, betas, eta, rand=rand, deltas=deltas)
    du = w["u"] - z["u"]
    de = w["e"] - z["e"]
    num = np.sqrt((du[:, :, N - 1] ** 2).sum(0))
    den = np.sqrt((du[:, :, 0] ** 2).sum(0))
    amp = num / den
    pk = np.abs(de).max(0)                     # (R,N)
    peak_growth = pk[:, N - 1] / np.maximum(pk[:, 1], 1e-9)
    dmin = w["gap"][:, :, 1:].min(axis=(0, 2))
    return dict(amp=amp, peak_growth=peak_growth, dmin=dmin,
                peak_e=pk[:, 1:].max(1))
