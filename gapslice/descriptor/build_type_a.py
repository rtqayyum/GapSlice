"""Type-A descriptor table: certified mean-square string-gain curves.

For every gap h, mean burst length beta (0 = independent losses) and
driveline time constant eta, the bounded-real-lemma SDP of Eq. (7) is solved
on a grid of delivery probabilities p. The descriptor p^A(beta; h, gamma) of
Eq. (8) is then read from these curves by monotone interpolation
(:func:`gapslice.descriptor.tables.p_c`).

Usage:  python -m gapslice.descriptor.build_type_a      (about 12 min, 2 cores)
Output: results/gain_curves.npz
"""
import numpy as np, itertools, time, sys
from multiprocessing import Pool
from gapslice import params as P
from gapslice import paths
from gapslice.control.mjls import gain_at, p_min_valid
from gapslice.control.certificate import GainSolver

H_LIST = np.round(np.concatenate([np.arange(0.3, 1.51, 0.1), [1.75, 2.0, 2.25, 2.5, 2.8]]), 2)
BETAS = [0.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]   # 0.0 encodes i.i.d. losses
ETAS = [0.30, 0.40]
ONE_MINUS_P = np.logspace(-4.5, np.log10(0.75), 64)


def beta_arg(b):
    return None if b == 0.0 else b


def curve(args):
    h, eta = args
    solver = GainSolver(float(h), float(eta))
    res = {}
    for b in BETAS:
        out = []
        for q in ONE_MINUS_P:
            p = 1.0 - q
            if p < p_min_valid(beta_arg(b)):
                out.append(np.nan); continue
            out.append(solver.gain(p, beta_arg(b)))
        res[b] = np.array(out)
    return (h, eta, res)


def main():
    from gapslice.descriptor import build_type_a as mod   # picklable workers
    t0 = time.time()
    jobs = list(itertools.product(H_LIST, ETAS))
    G = np.full((len(H_LIST), len(BETAS), len(ETAS), len(ONE_MINUS_P)), np.nan)
    G1 = np.full((len(H_LIST), len(ETAS)), np.nan)   # p = 1 (no loss)
    with Pool(2) as pool:
        for k, (h, eta, res) in enumerate(pool.imap_unordered(mod.curve, jobs)):
            i = list(H_LIST).index(h); m = ETAS.index(eta)
            for b, g in res.items():
                G[i, BETAS.index(b), m] = g
            if (k + 1) % 6 == 0:
                print(f"{k+1}/{len(jobs)}  {time.time()-t0:.0f}s", flush=True)
    for i, h in enumerate(H_LIST):
        for m, eta in enumerate(ETAS):
            G1[i, m] = gain_at(float(h), 1.0, None, float(eta))
    np.savez(paths.out("gain_curves.npz"), H=H_LIST, BETAS=np.array(BETAS),
             ETAS=np.array(ETAS), Q=ONE_MINUS_P, G=G, G1=G1)
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
