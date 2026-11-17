"""Diagnostic experiments for revision planning, not final-paper validation.

The inherited FBL approximation, controller, descriptor interpolation and
illustrative utilities remain in use. Each family isolates a limitation;
none claims a newly proved outcome, safety, privacy or NR guarantee.
"""
from functools import lru_cache
import time
import warnings

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.special import ndtr

from gapslice import params as P
from gapslice.channel import link
from gapslice.descriptor.tables import p_c
from gapslice.stats import wilson
from gapslice.revision.radio_budget import RadioBudget


@lru_cache(maxsize=512)
def radio_errors(h, blocked, n_trucks, cap, payload, rice, power_aware):
    radio = RadioBudget(cap)
    eps = P.eps_link(n_trucks - 1)
    z = link.design_sinr_db(h, blocked, eps)
    fade_margin = link.mean_sinr_db(h, blocked) - z
    desired_loss = link.pathloss_db(P.antenna_distance(h)) + (P.BLOCK_MU_DB if blocked else 0)
    interfering_losses = [link.pathloss_db(P.REUSE_D)] * P.N_INTERF
    values = []
    for b in range(1, cap + 1):
        snr = (radio.sinr_db(desired_loss, interfering_losses, b) - fade_margin
               if power_aware else z)
        values.append(link.attempt_error(b * P.N_RE_PRB, snr, rice_k_db=rice, L=payload*8))
    return np.array(values)


def best_plan(target, errors, max_attempts=4):
    best = None
    for m in range(1, max_attempts + 1):
        feasible = np.flatnonzero(1 - errors**m >= target)
        if feasible.size:
            b = int(feasible[0]) + 1
            candidate = dict(prb_slots=m*b, attempts=m, prbs_per_attempt=b)
            if best is None or m*b < best['prb_slots']:
                best = candidate
    return best


def radio_task(c):
    pc = p_c(c['h'], c['beta'], P.GAMMA_LINK, c['eta'])
    if not np.isfinite(pc):
        return dict(supported=False, reason='Legacy type-A descriptor unavailable at this gap')
    z = link.design_sinr_db(c['h'], c['blocked'], P.eps_link(c['n_trucks']-1))
    result = {}
    for kind, target in [('descriptor_A', float(pc)), ('fixed_9999', 0.9999)]:
        total, m, b = link.prbs_for_target(target, z, rice_k_db=c['rice'], L=8*c['payload'])
        plans = {}
        for aware in [False, True]:
            e = radio_errors(c['h'], c['blocked'], c['n_trucks'], c['cap'],
                             c['payload'], c['rice'], aware)
            plans['power_aware' if aware else 'fixed_reference_sinr'] = best_plan(target, e)
        result[kind] = dict(target=target, inherited_prb_slots=float(total),
                            inherited_attempts=m, inherited_prbs_per_attempt=b,
                            inherited_plan_fits_slot=bool(np.isfinite(total) and b <= c['cap']),
                            capped_plans=plans)
    return dict(supported=True, comparison=result,
                limitations='One-slot copies, independent fast fading, old FBL approximation; no NR overhead/BLER calibration')


def fading_task(c):
    """Correlate diffuse complex fading across blind copies, not packet time."""
    rng = np.random.default_rng(c['seed'])
    n = c['replicates']
    z = (rng.standard_normal((n, 4)) + 1j*rng.standard_normal((n, 4))) / np.sqrt(2)
    common = (rng.standard_normal((n, 1)) + 1j*rng.standard_normal((n, 1))) / np.sqrt(2)
    diffuse = np.sqrt(c['rho'])*common + np.sqrt(1-c['rho'])*z
    k = 10**(c['rice']/10)
    gains = np.sqrt(k/(k+1)) + diffuse/np.sqrt(k+1)
    snr = 10**(link.design_sinr_db(c['h'], False)/10)
    e = link.fbl_error(c['b']*P.N_RE_PRB, snr*np.abs(gains)**2)
    rows = []
    for m in [1, 2, 4]:
        conditional_loss = np.prod(e[:, :m], axis=1)
        mean = float(conditional_loss.mean())
        se = float(conditional_loss.std(ddof=1)/np.sqrt(n))
        rows.append(dict(attempts=m, loss_estimate=mean, standard_error=se,
                         approximate_95_interval=[max(0., mean-1.96*se), min(1., mean+1.96*se)],
                         product_of_marginal_error_estimates=float(np.prod(e[:, :m].mean(axis=0)))))
    return dict(rows=rows, replicates=n,
                limitations='Synthetic correlated Rician diffuse components; conditional decoding errors independent. Intervals are Monte Carlo approximations, not rare-event certificates.')


def control_task(c):
    """Stress the inherited constant-gap control model with common link losses."""
    from gapslice.simulation.vectorized import braking_pulse, disturbance_metrics
    target = p_c(c['h'], c['beta'], P.GAMMA_LINK, c['eta'])
    if not np.isfinite(target):
        return dict(supported=False, reason='Legacy type-A descriptor unavailable at this gap')
    p = float(np.clip(target+c['delivery_margin'], 1e-6, 1))
    n_links, r, steps = c['n_trucks']-1, c['replicates'], 360
    rng = np.random.default_rng(c['seed'])
    shared = rng.standard_normal((steps, r, 1))
    individual = rng.standard_normal((steps, r, n_links))
    uniforms = ndtr(np.sqrt(c['rho'])*shared + np.sqrt(1-c['rho'])*individual)
    del individual, shared
    good = np.ones((r, n_links), dtype=bool)
    d = np.zeros((steps, r, n_links), dtype=bool)
    recovery = p if c['beta'] == 0 else min(1/c['beta'], p/max(1-p, 1e-12))
    onset = 1-p if c['beta'] == 0 else min(1., recovery*(1-p)/p)
    for t in range(steps):
        good = np.where(good, uniforms[t] >= onset, uniforms[t] < recovery)
        d[t] = good
    del uniforms
    amp, duration = (-3., 1.5) if c['brake'] == 'moderate' else (-6., 2.)
    u0, _ = braking_pulse(steps, r, rng, 2., 6., amp=amp, dur=duration)
    metrics = disturbance_metrics(u0, c['n_trucks'], np.full(steps, c['h']), None,
                                  [c['beta']]*n_links, c['eta'], seed=c['seed'], deltas=d)
    events = int(np.sum(metrics['peak_growth'] > 1.05))
    return dict(supported=True, delivery_probability=p, descriptor_target=float(target),
                growth_events=events, braking_events=r, event_fraction=events/r,
                pointwise_wilson_95=wilson(events, r),
                mean_square_pulse_gain=float(np.sqrt(np.mean(metrics['amp']**2))),
                finite_platoon_gain_bound=P.GAMMA_LINK**n_links,
                minimum_distance_01_quantile_m=float(np.quantile(metrics['dmin'], .01)),
                observed_nonpositive_distance=int(np.sum(metrics['dmin'] <= 0)),
                maximum_spacing_error_99_quantile_m=float(np.quantile(metrics['peak_e'], .99)),
                limitations='Inherited linear constant-gap model, ideal radar and no new delay/actuator model. rho is latent cross-link correlation; correlated-link cases are outside the independent-link certificate. Observed distances are not safety guarantees.')


def market_task(c):
    """Use both total and ACC-relative utility; report solver status honestly."""
    from gapslice.scenario.tenants import draw_tenants
    from gapslice.allocation.market import price_only_market, evaluate, greedy_fixed
    tenants = draw_tenants(c['tenants'], c['seed'], contract=c['contract'])
    start = time.perf_counter()
    menus = [t.menu('ceb') for t in tenants]
    menu_s = time.perf_counter()-start
    start = time.perf_counter()
    chosen, info = price_only_market(tenants, c['pool'], seed=c['seed'], return_info=True)
    market_s = time.perf_counter()-start
    baseline = float(sum(t.U(P.H_ACC) for t in tenants))
    market = evaluate(tenants, chosen, c['pool'])
    fixed = evaluate(tenants, greedy_fixed(tenants, c['pool'], 'ceb'), c['pool'])
    if not market['feasible'] or not fixed['feasible']:
        raise AssertionError('Capacity-violating inherited allocation')
    costs, values, owner = [], [], []
    for k, menu in enumerate(menus):
        for h, b, u in menu:
            costs.append(b); values.append(u-tenants[k].U(P.H_ACC)); owner.append(k)
    eq = np.zeros((len(tenants), len(costs)))
    eq[owner, np.arange(len(costs))] = 1
    costs, values = np.array(costs), np.array(values)
    # SciPy forwards these HiGHS options; constrain each rank to one solver thread.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Unrecognized options detected.*')
        warnings.filterwarnings('ignore', message='Unrecognized options.*')
        lp = linprog(-values, A_ub=costs[None, :], b_ub=[c['pool']], A_eq=eq,
                     b_eq=np.ones(len(tenants)), bounds=(0, 1), method='highs', options={'threads': 1})
        if not lp.success:
            raise RuntimeError(f'LP reference failed: {lp.message}')
        exact = None
        if c['tenants'] <= 80:
            start = time.perf_counter()
            mip = milp(-values, integrality=np.ones(len(costs)), bounds=Bounds(0, 1),
                       constraints=[LinearConstraint(costs[None, :], -np.inf, c['pool']),
                                    LinearConstraint(eq, 1, 1)],
                       options={'threads': 1, 'time_limit': 30., 'mip_rel_gap': 0.})
            exact = dict(status=int(mip.status), proven_optimal=bool(mip.status == 0),
                         runtime_s=time.perf_counter()-start,
                         incremental_utility=None if mip.fun is None else float(-mip.fun),
                         relative_gap=None if getattr(mip, 'mip_gap', None) is None else float(mip.mip_gap))
    upper = float(-lp.fun)
    increment = market['utility']-baseline
    return dict(market=market, fixed=fixed, acc_utility=baseline, incremental_utility=increment,
                lp_incremental_upper_bound=upper,
                incremental_ratio_to_lp_upper_bound=None if upper <= 1e-12 else increment/upper,
                exact_reference=exact, menu_build_s=menu_s, market_s=market_s, price_rounds=info['rounds'],
                limitations='Inherited abstract resource pool and illustrative utility; no new sidelink scheduling, formal privacy or approximation guarantee. LP ratio is an empirical certificate against this instance upper bound.')


DISPATCH = dict(radio=radio_task, fading=fading_task, control=control_task, market=market_task)
