"""Control side of GapSlice: MJLS model of a CACC follower under bursty
packet loss, mean-square stability, mean-square l2 gain via the stochastic
bounded-real lemma, and the control descriptor p_c.

State of follower i (deviation coordinates):
    xi = [e, dv, a_{i-1}, a_i, u_i, uhat]
input  w = u_{i-1} (predecessor's desired acceleration)
output y = u_i
Mode sigma in {0..K}: 0 = CAM of this period delivered, j = j consecutive
losses; mode K = ACC fallback (feed-forward set to zero).
"""
import numpy as np
import cvxpy as cp
from functools import lru_cache
from gapslice import params as P
def zoh_coeffs(eta, T=P.T):
    c5 = np.exp(-T / eta)
    c6 = 1.0 - c5
    c3 = eta * (1.0 - c5)
    c4 = T - eta * (1.0 - c5)
    c1 = eta * (T - eta * (1.0 - c5))
    c2 = T ** 2 / 2 - eta * T + eta ** 2 * (1.0 - c5)
    return c1, c2, c3, c4, c5, c6


def mode_matrices(h, eta=P.ETA_DEFAULT, K=P.K_FALLBACK, kp=P.KP, kd=P.KD, T=P.T):
    """Return lists A[j], B[j] (j = 0..K) and C."""
    c1, c2, c3, c4, c5, c6 = zoh_coeffs(eta, T)
    g = T / h
    A0 = np.zeros((6, 6))
    B0 = np.zeros((6, 1))
    # e+
    A0[0, :] = [1, T, c1, -(c1 + h * c3), -(c2 + h * c4), 0]
    B0[0, 0] = c2
    # dv+
    A0[1, :] = [0, 1, c3, -c3, -c4, 0]
    B0[1, 0] = c4
    # a_{i-1}+
    A0[2, 2] = c5
    B0[2, 0] = c6
    # a_i+
    A0[3, 3] = c5
    A0[3, 4] = c6
    # u_i+ = u + g(-u + kp e + kd (dv - h a_i) + uhat)
    A0[4, :] = [g * kp, g * kd, 0, -g * kd * h, 1 - g, g]
    A, B = [], []
    for j in range(K + 1):
        Aj, Bj = A0.copy(), B0.copy()
        if j == 0:            # delivered: uhat+ = u_{i-1}
            Aj[5, 5] = 0.0
            Bj[5, 0] = 1.0
        elif j < K:           # lost, hold
            Aj[5, 5] = 1.0
        else:                 # fallback to ACC: feed-forward zeroed
            Aj[5, 5] = 0.0
        A.append(Aj)
        B.append(Bj)
    C = np.zeros((1, 6))
    C[0, 4] = 1.0
    return A, B, C


def tpm(p, beta=None, K=P.K_FALLBACK):
    """Transition matrix of the loss-counter mode.
    beta=None -> i.i.d. Bernoulli losses (recovery prob = p);
    beta>0     -> Gilbert channel with mean loss-burst length beta."""
    if beta is None:
        alpha, rho = 1.0 - p, p
    else:
        rho = 1.0 / beta
        alpha = rho * (1.0 - p) / p
    if alpha > 1.0 + 1e-12:
        raise ValueError("infeasible (p, beta): need p >= 1/(1+beta)")
    alpha = min(alpha, 1.0)
    Pi = np.zeros((K + 1, K + 1))
    Pi[0, 0], Pi[0, 1] = 1 - alpha, alpha
    for j in range(1, K + 1):
        Pi[j, 0] = rho
        Pi[j, min(j + 1, K)] += 1 - rho
    return Pi


def p_min_valid(beta):
    return 0.0 if beta is None else 1.0 / (1.0 + beta) + 1e-9


def ms_radius(A, Pi):
    """Spectral radius of the second-moment operator (MSS iff < 1)."""
    n = A[0].shape[0]
    M = len(A)
    big = np.zeros((M * n * n, M * n * n))
    for i in range(M):
        AA = np.kron(A[i], A[i])
        for j in range(M):
            if Pi[i, j] != 0:
                big[j * n * n:(j + 1) * n * n, i * n * n:(i + 1) * n * n] += Pi[i, j] * AA
    return max(abs(np.linalg.eigvals(big)))


def ms_gain(A, B, C, Pi, solver="CLARABEL"):
    """Mean-square l2 gain (stochastic bounded-real lemma). Returns inf if
    the jump system is not mean-square stable or the SDP is infeasible."""
    if ms_radius(A, Pi) >= 1.0 - 1e-9:
        return np.inf
    M = len(A)
    n = A[0].shape[0]
    Ps = [cp.Variable((n, n), symmetric=True) for _ in range(M)]
    g2 = cp.Variable()
    cons = []
    for j in range(M):
        E = sum(Pi[j, m] * Ps[m] for m in range(M) if Pi[j, m] != 0)
        Aj, Bj = A[j], B[j]
        top_l = Aj.T @ E @ Aj - Ps[j] + C.T @ C
        top_r = Aj.T @ E @ Bj
        bot_r = Bj.T @ E @ Bj - g2 * np.eye(1)
        blk = cp.bmat([[top_l, top_r], [top_r.T, bot_r]])
        blk = (blk + blk.T) / 2
        cons += [blk << -1e-7 * np.eye(n + 1), Ps[j] >> 1e-7 * np.eye(n)]
    prob = cp.Problem(cp.Minimize(g2), cons)
    try:
        prob.solve(solver=solver)
    except Exception:
        try:
            prob.solve(solver="SCS", eps=1e-7, max_iters=200000)
        except Exception:
            return np.inf
    if prob.status not in ("optimal", "optimal_inaccurate") or g2.value is None:
        return np.inf
    return float(np.sqrt(max(g2.value, 0.0)))


@lru_cache(maxsize=None)
def gain_at(h, p, beta, eta=P.ETA_DEFAULT, K=P.K_FALLBACK):
    A, B, C = mode_matrices(h, eta, K)
    if p >= 1.0 - 1e-12:
        Pi = np.zeros((K + 1, K + 1)); Pi[:, 0] = 1.0
    else:
        Pi = tpm(p, beta, K)
    return ms_gain(A, B, C, Pi)


def lti_hinf(h, eta=P.ETA_DEFAULT, mode=0, K=P.K_FALLBACK, n_w=4000):
    """H-inf norm of the deterministic system with a fixed mode (0 = ideal
    CACC, K = ACC) by a dense frequency sweep (used as a cross-check)."""
    A, B, C = mode_matrices(h, eta, K)
    Aj, Bj = A[mode], B[mode]
    w = np.linspace(1e-4, np.pi, n_w)
    best = 0.0
    for wk in w:
        z = np.exp(1j * wk)
        G = C @ np.linalg.solve(z * np.eye(6) - Aj, Bj)
        best = max(best, abs(G[0, 0]))
    if max(abs(np.linalg.eigvals(Aj))) >= 1:
        return np.inf
    return best


def p_critical(h, beta, gamma, eta=P.ETA_DEFAULT, tol=2e-4):
    """Control descriptor: smallest p with ms_gain <= gamma (bisection).
    Returns (p_c, ok) where ok=False if even p=1 fails."""
    if gain_at(round(h, 4), 1.0, beta, eta) > gamma:
        return np.nan, False
    lo = p_min_valid(beta)
    if gain_at(round(h, 4), round(lo + 1e-6, 6), beta, eta) <= gamma:
        return lo, True
    hi = 1.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if gain_at(round(h, 4), round(mid, 6), beta, eta) <= gamma:
            hi = mid
        else:
            lo = mid
    return hi, True


# ---------------- Lyapunov decay rates for stability loans ----------------
def decay_certificate(A, Pi, iters=30):
    """Largest lambda_s with A_j' E_j(P) A_j <= (1-lambda_s) P_j (bisection);
    returns (lambda_s, [P_j])."""
    M, n = len(A), A[0].shape[0]
    lo, hi, bestP = 0.0, 1.0, None
    for _ in range(iters):
        lam = 0.5 * (lo + hi)
        Ps = [cp.Variable((n, n), symmetric=True) for _ in range(M)]
        cons = []
        for j in range(M):
            E = sum(Pi[j, m] * Ps[m] for m in range(M) if Pi[j, m] != 0)
            X = A[j].T @ E @ A[j] - (1 - lam) * Ps[j]
            cons += [(X + X.T) / 2 << 0, Ps[j] >> np.eye(n)]
        prob = cp.Problem(cp.Minimize(0), cons)
        try:
            prob.solve(solver="CLARABEL")
            ok = prob.status in ("optimal", "optimal_inaccurate")
        except Exception:
            ok = False
        if ok:
            lo, bestP = lam, [Pk.value for Pk in Ps]
        else:
            hi = lam
    return lo, bestP


def growth_factor(A, Pi_def, Ps):
    """1+lambda_u: worst one-step growth of V under a deficit TPM, w.r.t. P."""
    M = len(A)
    worst = 0.0
    for j in range(M):
        E = sum(Pi_def[j, m] * Ps[m] for m in range(M))
        X = A[j].T @ E @ A[j]
        L = np.linalg.cholesky((Ps[j] + Ps[j].T) / 2)
        Li = np.linalg.inv(L)
        S = Li @ X @ Li.T
        worst = max(worst, max(np.linalg.eigvalsh((S + S.T) / 2)))
    return worst
