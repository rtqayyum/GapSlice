"""Monte Carlo estimate of the mean-square l2 gain of the jump system:
gain^2 = lambda_max( E[H' H] ), H = random impulse-response (Toeplitz-free)
matrix over a finite horizon, for a given initial-mode law."""
import numpy as np
from gapslice import params as P
from gapslice.control.mjls import mode_matrices, tpm


def stationary(Pi):
    w, v = np.linalg.eig(Pi.T)
    k = np.argmin(abs(w - 1))
    s = np.real(v[:, k]); s = s / s.sum()
    return np.clip(s, 0, None) / np.clip(s, 0, None).sum()


def mc_gain(h, p, beta, eta=P.ETA_DEFAULT, S=240, R=3000, init="stationary",
            seed=0, K=P.K_FALLBACK):
    rng = np.random.default_rng(seed)
    A, B, C = mode_matrices(h, eta, K)
    A = np.stack(A); B = np.stack(B)[:, :, 0]
    Pi = tpm(p, beta, K)
    cum = np.cumsum(Pi, axis=1)
    if init == "stationary":
        pi0 = stationary(Pi)
        modes = rng.choice(K + 1, size=R, p=pi0)
    else:
        modes = np.full(R, int(init))
    X = np.zeros((R, 6, S))           # column s: response to impulse at s
    M = np.zeros((S, S))
    for t in range(S):
        Y = X[:, 4, :]                 # output u_i at time t, all impulses
        M += Y.T @ Y
        At = A[modes]                  # (R,6,6)
        X = np.einsum("rij,rjs->ris", At, X)
        X[:, :, t] += B[modes]         # impulse applied at time t
        r = rng.random(R)
        modes = (r[:, None] > cum[modes]).sum(axis=1)
    M /= R
    return float(np.sqrt(max(np.linalg.eigvalsh((M + M.T) / 2))))
