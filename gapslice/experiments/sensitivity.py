"""Sensitivity analysis (supplementary Section S7).

  1. payload size      : 300, 600, 1200 B (TS 22.186 range is 50-1200 B)
  2. contract tolerance: per-vehicle gain 1.0025^{2.5, 5, 10}
  3. fading/diversity  : Rayleigh, Rician K = 10 dB, 2-Rx MRC (each used both
                         for planning and as the true channel)
  4. channel-model error: the reservation of one link of a 5-truck platoon
                         (eps_l = 1.25 %) is planned with the nominal model
                         (per slow state, LOS, d_c = 10 m, i.i.d. fast losses),
                         but the true channel differs:
                           Rayleigh instead of Rician K = 3 dB,
                           large-scale std +2 dB,
                           interferers at 200 m instead of 300 m,
                           mean SINR -3 dB.
                         We report the certified gain over the joint modes of
                         the true chain (states above its eps-quantile), and
                         the detection rate of an online loss-rate check with
                         5 % false alarms (sidelink HARQ feedback, A1).

Usage:  python -m gapslice.experiments.sensitivity
Output: results/sens.json
"""
import json, time
import numpy as np
from gapslice import params as P
from gapslice import paths
from gapslice.channel import fsmc as CT
from gapslice.descriptor.tables import p_c, load_curves
from gapslice.allocation.ceb import rel_class
from gapslice.channel.link import design_sinr_db, mean_sinr_db, prbs_for_target, delivery_prob
from scipy.stats import norm

H_LIST = [0.6, 0.8, 1.0, 1.2]


def prb(p, sinr, **kw):
    if not np.isfinite(p):
        return np.inf
    return prbs_for_target(float(p), float(sinr), **kw)[0]


def fin(x):
    return None if not np.isfinite(x) else float(x)


def part_payload():
    rows = []
    for LB in [300, 600, 1200]:
        for beta in [0.0, 2.0]:
            for h in H_LIST:
                s = design_sinr_db(h)
                pc = p_c(h, beta, P.GAMMA_LINK)
                rows.append(dict(payload=LB, beta=beta, h=h, p_c=fin(pc),
                                 ceb=fin(prb(pc, s, L=8 * LB)),
                                 cls=fin(prb(rel_class(pc), s, L=8 * LB)),
                                 urllc=fin(prb(P.P_URLLC, s, L=8 * LB))))
    return rows


def part_tolerance():
    rows = []
    for ex in [2.5, 5.0, 10.0]:
        g = P.GAMMA_UNIT ** ex
        for beta in [0.0, 2.0, 4.0]:
            hs = [float(h) for h in load_curves()["H"] if h < P.H_ACC - 1e-9]
            feas = [h for h in hs if np.isfinite(p_c(h, beta, g))]
            row = dict(exp=ex, gamma=g, beta=beta, h_min=min(feas) if feas else None, at={})
            for h in H_LIST:
                pc = p_c(h, beta, g)
                s = design_sinr_db(h)
                row["at"][str(h)] = dict(p_c=fin(pc), ceb=fin(prb(pc, s)),
                                         urllc=fin(prb(P.P_URLLC, s)))
            rows.append(row)
    return rows


def part_radio():
    rows = []
    for name, kw in [("Rician K=3 dB (nominal)", dict(rice_k_db=3.0, n_rx=1)),
                     ("Rayleigh", dict(rice_k_db=-np.inf, n_rx=1)),
                     ("Rician K=10 dB", dict(rice_k_db=10.0, n_rx=1)),
                     ("K=3 dB, 2-Rx MRC", dict(rice_k_db=3.0, n_rx=2))]:
        for beta in [0.0, 2.0]:
            for h in H_LIST:
                s = design_sinr_db(h)
                pc = p_c(h, beta, P.GAMMA_LINK)
                rows.append(dict(radio=name, beta=beta, h=h, ceb=fin(prb(pc, s, **kw)),
                                 urllc=fin(prb(P.P_URLLC, s, **kw))))
    return rows


def availability(h, m, b, pc, sigma, shift, kw):
    """Exact share of time in which the delivery probability of reservation
    (m, b) is at least p_c: Pr[x >= x*], where p(x*) = p_c (bisection)."""
    s0 = mean_sinr_db(h) + shift
    lo, hi = -60.0, 60.0
    if delivery_prob(b, m, s0 + lo, **kw) >= pc:
        return 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if delivery_prob(b, m, s0 + mid, **kw) >= pc:
            hi = mid
        else:
            lo = mid
    return float(norm.sf(hi / sigma))


def loss_rate(Pt, ps, W, n, rng):
    d = CT.traces(Pt, ps, W, n, 1, rng)[:, :, 0]
    return 1.0 - d.mean(axis=0)


def part_model_error(n_win=4000):
    sig0 = CT.sigma_ls(False)
    rho = CT.rho_of(CT.DC_LOS)
    x0, pi0, Pt0, av0, xe0 = CT.fsmc(sig0, rho)
    Q0 = CT.restrict(Pt0, av0)
    errors = [("nominal", {}),
              ("Rayleigh fading", dict(kw=dict(rice_k_db=-np.inf))),
              ("large-scale std +2 dB", dict(sigma=sig0 + 2.0)),
              ("interferers at 200 m", dict(reuse=200.0)),
              ("mean SINR -3 dB", dict(shift=-3.0))]
    rows = []
    for h in H_LIST:
        pc = p_c(h, 0.0, P.GAMMA_LINK)
        tot, m, b = prbs_for_target(pc, mean_sinr_db(h) + xe0)
        ps_nom_full = CT.state_probs(h, False, m, b, x0)
        for name, e in errors:
            t1 = time.time()
            sig = e.get("sigma", sig0)
            x, pi, Pt, av, xe = CT.fsmc(sig, rho)
            Q = CT.restrict(Pt, av)
            shift = e.get("shift", 0.0)
            if "reuse" in e:
                shift = mean_sinr_db(h, reuse_d=e["reuse"]) - mean_sinr_db(h)
            kw = e.get("kw", {})
            ps = CT.state_probs(h, False, m, b, x[av], mean_shift_db=shift, **kw)
            ps_full = CT.state_probs(h, False, m, b, x, mean_shift_db=shift, **kw)
            g = CT.joint_gain(h, Q, ps)
            # share of time in which the per-state target p_c is still met
            met = availability(h, m, b, pc, sig, shift, kw)
            det = {}
            for wname, W in [("10 s", 300), ("30 s", 900)]:
                rng = np.random.default_rng(int(1000 * h) + W)
                l0 = loss_rate(Pt0, ps_nom_full, W, n_win, rng)
                thr = float(np.quantile(l0, 0.95))
                l1 = loss_rate(Pt, ps_full, W, n_win, rng)
                det[wname] = dict(threshold=thr, false_alarm=float(np.mean(l0 > thr)),
                                  detection=float(np.mean(l1 > thr)))
            rows.append(dict(h=h, error=name, p_c=pc, prbs=int(tot), m=int(m), b=int(b),
                             p_min=float(ps.min()), gain=g, share_met=met,
                             platoon_avail=max(0.0, 1.0 - P.N_LINKS_REF * (1.0 - met)),
                             online=det))
            print(f"  h={h} {name:24s}: p_min={ps.min():.4f} (p_c={pc:.4f}) gain={g:.4f} "
                  f"time share meeting p_c={100*met:.1f}% det10={det['10 s']['detection']:.3f} "
                  f"det30={det['30 s']['detection']:.3f}  {time.time()-t1:.0f}s", flush=True)
    return rows


if __name__ == "__main__":
    t0 = time.time()
    out = dict(payload=part_payload())
    print("payload done", time.time() - t0, flush=True)
    out["tolerance"] = part_tolerance()
    print("tolerance done", time.time() - t0, flush=True)
    out["radio"] = part_radio()
    print("radio done", time.time() - t0, flush=True)
    out["model_error"] = part_model_error()
    json.dump(out, open(paths.out("sens.json"), "w"), indent=1, default=float)
    for r in out["payload"]:
        print(f"L={r['payload']}B beta={r['beta']} h={r['h']}: CEB={r['ceb']} class={r['cls']} 99.99%={r['urllc']}")
    for r in out["tolerance"]:
        a = r["at"]["1.0"]
        print(f"tol 1.0025^{r['exp']} beta={r['beta']}: h_min={r['h_min']} at 1.0 s CEB={a['ceb']} vs {a['urllc']}")
    for r in out["radio"]:
        print(f"{r['radio']:24s} beta={r['beta']} h={r['h']}: CEB={r['ceb']} 99.99%={r['urllc']}")
    print("done", time.time() - t0)
