"""The Markov-jump model (Section III-B) reproduces an independent
simulator of the trucks in physical units, and the two platoon simulators
(scalar and vectorized) agree run by run."""
import numpy as np
from gapslice import params as P
from gapslice.control.mjls import mode_matrices
from gapslice.simulation.platoon import simulate
from gapslice.simulation.vectorized import run


def test_mjls_matches_physical_simulator():
    rng = np.random.default_rng(1)
    S, h = 600, 0.6
    u0 = np.zeros(S); u0[30:90] = -2.0; u0[200:260] = 1.0
    deltas = (rng.random((S, 2)) < 0.7).astype(int)
    out = simulate(u0, 2, lambda t: h, None, deltas=deltas)
    A, B, C = mode_matrices(h)
    xi = np.zeros((6, 1)); lost = 0; y = []
    for t in range(S):
        y.append((C @ xi)[0, 0])
        lost = 0 if deltas[t, 1] else min(lost + 1, P.K_FALLBACK)
        xi = A[lost] @ xi + B[lost] * u0[t]
    err = np.max(np.abs(out["u"][:, 1] - np.array(y)))
    print(f"max |u_phys - u_mjls| = {err:.2e}")
    assert err < 1e-9


def test_vectorized_matches_scalar_simulator():
    rng = np.random.default_rng(3)
    S, N, p, beta = 400, 5, 0.8, 2.0
    u0 = np.zeros(S); u0[50:95] = -3; u0[95:140] = 1.5
    rand = rng.random((S, 1, N - 1))
    out = run(u0[None, :], N, np.full(S, 0.6), np.full((S, N - 1), p), [beta] * 4, rand=rand)
    # rebuild the delivery indicators of the vectorized Gilbert channel
    good = np.ones(N, bool); deltas = np.zeros((S, N), int)
    rho = 1 / beta; alpha = min(1, rho * (1 - p) / p)
    for t in range(S):
        for i in range(1, N):
            x = rand[t, 0, i - 1]
            ok = (x >= alpha) if good[i] else (x < rho)
            good[i] = ok; deltas[t, i] = int(ok)
    ref = simulate(u0, N, lambda t: 0.6, None, deltas=deltas)
    du = np.abs(out["u"][:, 0, :] - ref["u"]).max()
    de = np.abs(out["e"][:, 0, :] - ref["e"]).max()
    print(f"max diff u {du:.2e}, e {de:.2e}")
    assert du < 1e-9 and de < 1e-9


if __name__ == "__main__":
    test_mjls_matches_physical_simulator()
    test_vectorized_matches_scalar_simulator()
    print("model consistency checks passed")
