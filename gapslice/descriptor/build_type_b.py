"""Type-B descriptor table: per-event risk of a hard brake.

Used by contract type B and by the type-B loan guard.

For every gap h, mean burst length beta (0 = independent losses), platoon
size N and driveline time constant eta, the tenant simulates its own platoon
under a hard brake of the leader at a random time and counts the events in
which the peak spacing error grows by more than 5 % from the first to the
last follower. The table stores the counts (k events out of n runs) on a
grid of loss probabilities 1-p, so that 95 % Wilson intervals can be formed.

Common random numbers are used across the p grid (same braking times and
same channel uniforms), so the estimated risk is coupled across p.

Usage:  python -m gapslice.descriptor.build_type_b      (about 85 min, 2 cores)
Output: results/tail_table.npz
"""
import itertools, time
import numpy as np
from multiprocessing import Pool
from gapslice import params as P
from gapslice import paths
from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics

GROWTH = 1.05                      # per-event growth threshold (type B)
H_LIST = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5,
          1.75, 2.0, 2.25, 2.5]
BETAS = [0.0, 2.0, 4.0]
NS = [3, 4, 5, 6, 7]
ETAS = [0.30, 0.40]
Q_GRID = np.array([1e-4, 3e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 3.5e-2, 5e-2,
                   7.5e-2, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5])
R = 3000                           # runs per grid point
S = int(12 / P.T)                  # 12 s horizon


def job(args):
    h, beta, eta, N = args
    rng = np.random.default_rng(1000 + int(100 * h) + 7 * N + int(10 * eta))
    u0, _ = braking_pulse(S, R, rng, 2.0, 6.0)
    k = np.full(len(Q_GRID), -1, dtype=int)
    for j, q in enumerate(Q_GRID):
        p = 1.0 - q
        if beta > 0 and p < 1.0 / (1.0 + beta):
            continue
        m = disturbance_metrics(u0, N, np.full(S, h), np.full((S, N - 1), p),
                                [beta] * (N - 1), eta, seed=4242 + N)
        k[j] = int(np.sum(m["peak_growth"] > GROWTH))
    return (h, beta, eta, N, k)


def main():
    from gapslice.descriptor import build_type_b as mod   # picklable workers
    t0 = time.time()
    jobs = list(itertools.product(H_LIST, BETAS, ETAS, NS))
    K = np.full((len(H_LIST), len(BETAS), len(ETAS), len(NS), len(Q_GRID)), -1, dtype=int)
    with Pool(2) as pool:
        for c, (h, b, eta, N, k) in enumerate(pool.imap_unordered(mod.job, jobs)):
            K[H_LIST.index(h), BETAS.index(b), ETAS.index(eta), NS.index(N)] = k
            if (c + 1) % 20 == 0:
                print(f"{c+1}/{len(jobs)}  {time.time()-t0:.0f}s", flush=True)
    np.savez(paths.out("tail_table.npz"), H=np.array(H_LIST), BETAS=np.array(BETAS),
             ETAS=np.array(ETAS), NS=np.array(NS), Q=Q_GRID, K=K, R=R, GROWTH=GROWTH)
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
