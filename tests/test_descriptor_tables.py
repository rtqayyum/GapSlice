"""The stored descriptor tables give the values reported in the paper, and
re-solving entries of the tables reproduces the stored numbers."""
import numpy as np
from gapslice import params as P
from gapslice.descriptor.tables import load_curves, load_tail_table, p_c, p_tail, interval_ok
from gapslice.control.certificate import GainSolver
from gapslice.control.mjls import p_min_valid
from gapslice.descriptor import build_type_a, build_type_b


def test_smallest_certifiable_gaps():
    # Section IV-B: 0.3 s (independent), 0.5 s (bursts of 2), 0.8 s (bursts of 4)
    D = load_curves()
    hs = [float(h) for h in D["H"] if h < P.H_ACC - 1e-9]
    for beta, h_min in [(0.0, 0.3), (2.0, 0.5), (4.0, 0.8)]:
        ok = [h for h in hs if np.isfinite(p_c(h, beta, P.GAMMA_LINK))]
        assert abs(min(ok) - h_min) < 1e-9


def test_tolerable_loss_at_one_second():
    # Section IV-B: 25 %, 23.5 % and 12.4 % lost CAMs at a gap of 1.0 s
    for beta, loss in [(0.0, 0.25), (2.0, 0.235), (4.0, 0.124)]:
        assert abs((1 - p_c(1.0, beta, P.GAMMA_LINK)) - loss) < 0.001


def test_type_b_descriptor_vs_platoon_size():
    # Section IV-B: 0.824 (3 trucks), 0.704 (5), 0.605 (7) at 1.0 s
    for N, val in [(3, 0.824), (5, 0.704), (7, 0.605)]:
        assert round(p_tail(1.0, 0.0, 0.3, N), 3) == val


def test_interval_property_on_grid():
    # supplementary material, Section S1: interval at all but one entry
    D = load_curves()
    bad = 0
    for h in D["H"]:
        for b in D["BETAS"]:
            for eta in D["ETAS"]:
                for j in range(1, 25):
                    if not interval_ok(float(h), float(b), P.GAMMA_UNIT ** j, float(eta)):
                        bad += 1
    assert bad <= 1


def test_type_a_entries_resolve_to_stored_values():
    D = load_curves()
    h, eta = 1.0, 0.3
    i, m = list(np.round(D["H"], 2)).index(h), list(D["ETAS"]).index(eta)
    solver = GainSolver(h, eta)
    for b in [0.0, 2.0, 4.0]:
        jb = list(D["BETAS"]).index(b)
        for k in [5, 30, 50]:
            p = 1.0 - D["Q"][k]
            if p < p_min_valid(build_type_a.beta_arg(b)):
                continue
            g = solver.gain(p, build_type_a.beta_arg(b))
            assert abs(g - D["G"][i, jb, m, k]) < 1e-6 * max(1, abs(g))


def test_type_b_entry_resimulates_to_stored_counts():
    T = load_tail_table()
    h, beta, eta, N = 1.0, 2.0, 0.3, 3
    _, _, _, _, k = build_type_b.job((h, beta, eta, N))
    i = list(T["H"]).index(h); j = list(T["BETAS"]).index(beta)
    m = list(T["ETAS"]).index(eta); n = list(T["NS"]).index(N)
    assert np.array_equal(k, T["K"][i, j, m, n])


if __name__ == "__main__":
    for f in [test_smallest_certifiable_gaps, test_tolerable_loss_at_one_second,
              test_type_b_descriptor_vs_platoon_size, test_interval_property_on_grid,
              test_type_a_entries_resolve_to_stored_values, test_type_b_entry_resimulates_to_stored_counts]:
        f(); print("ok", f.__name__)
