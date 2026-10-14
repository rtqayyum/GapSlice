"""Time-correlated channel for GapSlice (Sections III-B and IV-C of the paper).

Two time scales:
  * slow state s[t]: large-scale SINR deviation x[t] (dB) of a link, a
    Gauss-Markov process with decorrelation distance d_c (3GPP TR 37.885,
    Table 6.2.3-1: 10 m LOS, 13 m NLOSv). Per CAM period the platoon travels
    v*T, so the AR(1) coefficient is exp(-v*T/d_c). x is quantized into a
    finite-state Markov channel (FSMC) whose bin edges put the
    eps-quantile of the large-scale SINR exactly on a bin boundary.
  * fast losses within a slow state: independent per CAM (fast fading
    decorrelates within milliseconds) or a Gilbert channel with mean burst
    length beta (bursts from short interference or blockage events).

A PRB reservation (m attempts, b PRBs each) fixes the delivery probability
p_s in every slow state through the short-packet link model
(gapslice.channel.link).

This module provides
  * the FSMC (states, stationary law, transition matrix),
  * delivery statistics of a reservation: time-averaged p and mean loss-run
    length beta over a chain,
  * the joint (slow state, loss counter) transition matrix and the
    certificate of Eq. (7) written over the joint modes,
  * explicit delivery traces for the platoon simulator.
"""
import numpy as np
import cvxpy as cp
from functools import lru_cache
from scipy.stats import norm
from gapslice import params as P
from gapslice.channel.link import mean_sinr_db, delivery_prob
from gapslice.control.mjls import mode_matrices

D_CAM = P.V0 * P.T                       # distance travelled per CAM period [m]
DC_LOS, DC_NLOSV = 10.0, 13.0            # TR 37.885 Table 6.2.3-1 [m]


def sigma_ls(blocked):
    return P.SIGMA_LS_DB if not blocked else float(np.hypot(P.SIGMA_LS_DB, P.BLOCK_SIGMA_DB))


# probability edges of the available bins (fraction of the available range):
# narrow near the eps-quantile, where the delivery probability changes
# fastest, and wide above it, where it is close to one
U_AVAIL = (0.0, 0.005, 0.015, 0.03, 0.055, 0.09, 0.14, 0.21, 0.31, 0.45, 0.65, 1.0)


@lru_cache(maxsize=None)
def fsmc(sigma, rho, eps=P.EPS_LINK_REF, n_out=2, u_avail=U_AVAIL):
    """Quantized Gauss-Markov large-scale process.
    eps is the per-link outage share (P.eps_link(L) for a platoon with L
    links; default: a link of the reference 5-truck platoon).
    Bins: n_out equiprobable outage bins below the eps-quantile and
    len(u_avail)-1 available bins above it (edges u_avail in probability).
    Returns (x_rep [dB], pi, Ptrans, avail_mask, x_eps)."""
    q_out = np.linspace(0.0, eps, n_out + 1)
    q_av = eps + (1.0 - eps) * np.asarray(u_avail)
    qe = np.concatenate([q_out[:-1], q_av])           # probability edges
    edges = sigma * norm.ppf(qe)                        # -inf ... +inf
    S = len(edges) - 1
    pi = np.diff(qe)
    # representative value: conditional median of each bin
    x_rep = sigma * norm.ppf((qe[:-1] + qe[1:]) / 2)
    # transition probabilities by integrating x over each bin
    Pt = np.zeros((S, S))
    sd = sigma * np.sqrt(max(1 - rho ** 2, 1e-12))
    for i in range(S):
        qq = np.linspace(qe[i], qe[i + 1], 402)[1:-1]   # interior quantiles
        x = sigma * norm.ppf(qq)                         # equiprobable points
        cdf = norm.cdf((edges[None, :] - rho * x[:, None]) / sd)   # (pts, S+1)
        Pt[i] = np.mean(np.diff(cdf, axis=1), axis=0)
    Pt = Pt / Pt.sum(axis=1, keepdims=True)
    avail = np.arange(S) >= n_out
    return x_rep, pi, Pt, avail, float(edges[n_out])


def rho_of(dc):
    return float(np.exp(-D_CAM / dc))


def state_probs(h, blocked, m, b, x_rep, mean_shift_db=0.0, **kw):
    """Delivery probability in every slow state for reservation (m, b)."""
    s0 = mean_sinr_db(h, blocked) + mean_shift_db
    return np.array([delivery_prob(b, m, s0 + x, **kw) if m > 0 else 0.0 for x in x_rep])


def restrict(Pt, mask):
    """Chain conditioned to stay in the states of mask (rows renormalized)."""
    Q = Pt[np.ix_(mask, mask)]
    return Q / Q.sum(axis=1, keepdims=True)


def stationary(Q):
    w, v = np.linalg.eig(Q.T)
    k = int(np.argmin(np.abs(w - 1)))
    s = np.abs(np.real(v[:, k]))
    return s / s.sum()


def loss_stats(Q, ps, beta=0.0):
    """Time-averaged delivery probability and mean loss-run length of the
    loss process: slow chain Q, per-state delivery ps, within-state
    independent losses (beta=0) or Gilbert bursts with mean length beta."""
    J = joint_tpm(Q, ps, beta, K=1)                     # modes (s, delivered/lost)
    pij = stationary(J)
    S = len(ps)
    lost = pij.reshape(S, 2)[:, 1].sum()
    # rate at which loss runs start: delivered -> lost transitions
    start = 0.0
    for s in range(S):
        for s2 in range(S):
            start += pij[2 * s] * J[2 * s, 2 * s2 + 1]
    pbar = 1.0 - lost
    bbar = lost / start if start > 0 else np.inf
    return float(pbar), float(bbar)


def counter_tpm(p, beta, K):
    """Loss-counter transition matrix within one slow state (rows: from j)."""
    p = float(np.clip(p, 1e-12, 1.0))
    if beta and beta > 0:
        rho = min(1.0 / beta, p / max(1.0 - p, 1e-12))   # bursts lengthen below 1/(1+beta)
        alpha = min(1.0, rho * (1.0 - p) / p)
    else:
        alpha, rho = 1.0 - p, p
    T = np.zeros((K + 1, K + 1))
    T[0, 0], T[0, 1] = 1 - alpha, alpha
    for j in range(1, K + 1):
        T[j, 0] = rho
        T[j, min(j + 1, K)] += 1 - rho
    return T


def joint_tpm(Q, ps, beta=0.0, K=P.K_FALLBACK):
    """Transition matrix over joint modes (s, j); slow state moves first,
    then the delivery in the new state follows that state's counter law."""
    S = len(ps)
    M = K + 1
    J = np.zeros((S * M, S * M))
    Ts = [counter_tpm(ps[s], beta, K) for s in range(S)]
    for s in range(S):
        for s2 in range(S):
            if Q[s, s2] == 0:
                continue
            J[s * M:(s + 1) * M, s2 * M:(s2 + 1) * M] = Q[s, s2] * Ts[s2]
    return J


def joint_gain(h, Q, ps, beta=0.0, eta=P.ETA_DEFAULT, K=P.K_FALLBACK):
    """Certified mean-square l2 gain (Eq. (7) over joint modes)."""
    A, B, C = mode_matrices(h, eta, K)
    S, M = len(ps), K + 1
    J = joint_tpm(Q, ps, beta, K)
    nm = S * M
    # mean-square stability check (second-moment operator)
    n = 6
    big = np.zeros((nm * n * n, nm * n * n))
    for i in range(nm):
        AA = np.kron(A[i % M], A[i % M])
        for j in range(nm):
            if J[i, j] != 0:
                big[j * n * n:(j + 1) * n * n, i * n * n:(i + 1) * n * n] += J[i, j] * AA
    if max(abs(np.linalg.eigvals(big))) >= 1 - 1e-9:
        return np.inf
    Ps = [cp.Variable((n, n), symmetric=True) for _ in range(nm)]
    g2 = cp.Variable()
    cons = []
    for i in range(nm):
        E = sum(J[i, j] * Ps[j] for j in range(nm) if J[i, j] > 1e-14)
        Ai, Bi = A[i % M], B[i % M]
        tl = Ai.T @ E @ Ai - Ps[i] + C.T @ C
        tr = Ai.T @ E @ Bi
        br = Bi.T @ E @ Bi - g2 * np.eye(1)
        blk = cp.bmat([[tl, tr], [tr.T, br]])
        cons += [(blk + blk.T) / 2 << -1e-8 * np.eye(n + 1), Ps[i] >> 1e-8 * np.eye(n)]
    prob = cp.Problem(cp.Minimize(g2), cons)
    try:
        prob.solve(solver="CLARABEL")
    except Exception:
        try:
            prob.solve(solver="SCS", eps=1e-8, max_iters=300000)
        except Exception:
            return np.inf
    if prob.status not in ("optimal", "optimal_inaccurate") or g2.value is None:
        return np.inf
    return float(np.sqrt(max(g2.value, 0.0)))


def traces(Q, ps, S_len, R, n_links, rng, beta=0.0, x0=None):
    """Delivery indicators (S_len, R, n_links) from the slow chain Q and the
    per-state delivery ps; slow states start from the stationary law."""
    Sn = len(ps)
    cum = np.cumsum(Q, axis=1)
    pi0 = stationary(Q)
    st = rng.choice(Sn, size=(R, n_links), p=pi0) if x0 is None else np.full((R, n_links), x0)
    ps = np.asarray(ps)
    out = np.zeros((S_len, R, n_links), dtype=bool)
    good = np.ones((R, n_links), dtype=bool)
    for t in range(S_len):
        u = rng.random((R, n_links))
        st = (u[..., None] > cum[st]).sum(axis=-1)
        st = np.minimum(st, Sn - 1)
        p = ps[st]
        v = rng.random((R, n_links))
        if beta and beta > 0:
            rho = np.minimum(1.0 / beta, p / np.maximum(1 - p, 1e-12))
            alpha = np.minimum(1.0, rho * (1 - p) / np.maximum(p, 1e-12))
            ok = np.where(good, v >= alpha, v < rho)
        else:
            ok = v < p
        good = ok
        out[t] = ok
    return out
