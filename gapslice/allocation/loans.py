"""Stability loans for priority surges (Section III-F, Algorithm 2).

A surge of priority demand arrives at time T_S. Free PRBs are used first;
the rest is borrowed from platoons:

* lender selection (:func:`compensation_clock`): an ascending compensation
  per released PRB with a step limit. Tenant k answers with the number of
  wider gap steps J_k that maximizes U_k(h^(j)) + omega * (b_k(h) - b_k(h^(j))),
  using its private utility and without bids;
* guarded release (:func:`guard_phi`): for each step h -> h' the lowest
  reservation between those of h' and h that satisfies the loan clause,
  Eq. (15), with the tables at h and the SINR at h'. Type A:
  prod_l gamma(h, p_l, beta) <= (1.0025^10)^(N-1); type B: 95 % upper bound
  of the per-event risk <= 5 %; loans only while the total loan time of the
  tenant in the epoch is at most T_LOAN.

Baseline release policies: wait-for-maneuver, graduated release, naive
preemption and static (lenders start at the next epoch).
"""
import numpy as np
from gapslice import params as P
from gapslice.descriptor.tables import gain_lookup, risk
from gapslice.scenario.tenants import flags_of
from gapslice.allocation.reservation import p_of, per_link

T_S = 5.0                     # surge time [s]
EPOCH = 30.0                  # admission epoch [s]
DV_MAX = 1.0                  # relative speed while opening a gap [m/s]
GAMMA_LOAN_EXP = 10.0         # per-link exponent of the clause (type A)
DELTA_LOAN = 0.05             # type B clause
T_LOAN = 10.0                 # max loan time per epoch [s]
KAPPA = 0.05                  # compensation-clock step
OMEGA0 = 1e-6
PHI = np.round(np.arange(0.0, 1.0001, 0.05), 2)
POLICIES = ["LTR (Alg. 2)", "Wait-for-maneuver", "Graduated", "Naive preemption", "Static"]


def t_tr(h, h2):
    """Duration [s] of a gap step h -> h2."""
    return (h2 - h) * P.V0 / DV_MAX


# ---------------------------------------------------------------- loan clause
def g_safe(h, p, beta, eta):
    if p <= 0:
        return np.inf
    g = gain_lookup(h, p, beta, eta)
    return g if np.isfinite(g) else np.inf


def metric(t, h, alloc, h_sinr=None):
    """Contracted metric of tenant t from the tables at gap h, with the
    delivery probability of each link at the SINR of gap h_sinr (the far end
    of a widening step, i.e. the lowest SINR of the step)."""
    fl = flags_of(t)
    hs = h if h_sinr is None else h_sinr
    ps = [p_of(n, hs, bf, P.eps_link(t.L)) for n, bf in zip(alloc, fl)]
    if t.contract == "A":
        return float(np.prod([g_safe(h, p, t.beta, t.eta) for p in ps]))
    pm = min(ps)
    if t.beta > 0 and pm < 1.0 / (1.0 + t.beta):
        return 1.0
    return risk(h, pm, t.beta, t.N, t.eta, upper=True)


def bound(t, kind, gexp=GAMMA_LOAN_EXP, dloan=DELTA_LOAN):
    """Contract bound (kind='contract') or loan-clause bound (kind='loan')."""
    if t.contract == "A":
        e = 5.0 if kind == "contract" else gexp
        return (P.GAMMA_UNIT ** e) ** t.L
    return 0.01 if kind == "contract" else dloan


def deficit(t, h, h2, phi):
    """Per-link reservation a fraction phi of the way from that of h2 to h."""
    a = per_link(t.contract, h, t.beta, flags_of(t), t.eta)
    c = per_link(t.contract, h2, t.beta, flags_of(t), t.eta)
    return tuple(int(np.ceil(y + phi * (x - y))) for x, y in zip(a, c))


def guard_phi(t, h, h2, gexp, dloan):
    """Lowest reservation between those of h2 and h meeting the clause with
    the tables at h and the SINR at h2 (worst corner of the step)."""
    lim = bound(t, "loan", gexp, dloan) * (1 + 1e-9)
    for phi in PHI:
        if metric(t, h, deficit(t, h, h2, phi), h2) <= lim:
            return float(phi)
    return 1.0


# ---------------------------------------------------------------- lenders
def compensation_clock(tenants, choice, need):
    """Ascending compensation clock with a step limit. The operator posts a
    compensation omega per released PRB and a step limit j_max; tenant k
    answers with the number of wider gap steps J_k <= j_max that maximizes
    U_k(h^(j)) + omega * (b_k(h) - b_k(h^(j))). The limit starts at one step
    (many short maneuvers release capacity fastest) and grows only when all
    tenants accept the limit and the release is still too small.
    Returns ({k: J_k}, rounds, omega, current menu indices)."""
    menus = [t.menu("ceb") for t in tenants]
    cur = [next(i for i, o in enumerate(m) if abs(o[0] - c[0]) < 1e-9) for m, c in zip(menus, choice)]
    omega, rounds, jmax = OMEGA0, 0, 1
    while True:
        rounds += 1
        J, rel, saturated = {}, 0.0, True
        for k, (m, i) in enumerate(zip(menus, cur)):
            h, b, u = m[i]
            top = min(jmax, len(m) - 1 - i)
            vals = [m[i + j][2] + omega * (b - m[i + j][1]) for j in range(top + 1)]
            jj = int(np.argmax(vals))
            if jj < top:
                saturated = False
            if jj > 0:
                J[k] = jj
                rel += b - m[i + jj][1]
        if rel >= need - 1e-9 or rounds > 5000:
            return J, rounds, omega, cur
        if saturated:
            jmax += 1
        else:
            omega *= 1 + KAPPA


def schedule(tenants, choice, need):
    """Gap steps of every lender: [(h, h2, b, b2, t_start, duration)]."""
    J, rounds, omega, cur = compensation_clock(tenants, choice, need)
    steps = {}
    for k, jj in J.items():
        m = tenants[k].menu("ceb")
        ts, st = T_S, []
        for j in range(cur[k], cur[k] + jj):
            h, b, _ = m[j]
            h2, b2, _ = m[j + 1]
            d = t_tr(h, h2)
            st.append((h, h2, b, b2, ts, d))
            ts += d
        steps[k] = st
    return steps, rounds, omega


def plan(tenants, steps, policy, gexp=GAMMA_LOAN_EXP, dloan=DELTA_LOAN, tloan=T_LOAN):
    """Release events [(time, PRBs)] and per-lender allocation plans."""
    events, plans = [], {}
    for k, st in steps.items():
        t = tenants[k]
        if policy == "Static":
            off = EPOCH - T_S
            for (h, h2, b, b2, ts, d) in st:
                events.append((ts + off + d, b - b2))
            continue
        phis, used = [], 0.0
        if policy == "Naive preemption":
            events.append((T_S, st[0][2] - st[-1][3]))
        for (h, h2, b, b2, ts, d) in st:
            if policy == "LTR (Alg. 2)":
                phi = guard_phi(t, h, h2, gexp, dloan) if used + d <= tloan + 1e-9 else 1.0
                if phi < 1.0:
                    used += d
                bdef = sum(deficit(t, h, h2, phi))
                events += [(ts, b - bdef), (ts + d, bdef - b2)]
                phis.append(phi)
            elif policy == "Graduated":
                for s_ in range(1, 21):
                    events.append((ts + d * s_ / 20, (b - b2) / 20))
            elif policy == "Wait-for-maneuver":
                events.append((ts + d, b - b2))
        plans[k] = dict(steps=st, phis=phis, loan_time=used)
    return events, plans


def alloc_at(t, st, phis, policy, j, frac):
    """Per-link allocation during step j at fraction frac of the step."""
    h, h2 = st[j][0], st[j][1]
    a = per_link(t.contract, h, t.beta, flags_of(t), t.eta)
    c = per_link(t.contract, h2, t.beta, flags_of(t), t.eta)
    if policy == "LTR (Alg. 2)":
        return deficit(t, h, h2, phis[j])
    if policy == "Naive preemption":
        return per_link(t.contract, st[-1][1], t.beta, flags_of(t), t.eta)
    if policy == "Graduated":
        return tuple(x + (y - x) * frac for x, y in zip(a, c))
    return a                                               # wait-for-maneuver


# ---------------------------------------------------------------- checks
def inst_metric(t, h, h2, alloc, frac):
    """Contracted metric at an intermediate gap h + frac*(h2-h) of a step,
    frozen at that instant: SINR at the current gap and the tables
    interpolated linearly between the grid gaps h and h2 (for type B the
    risk table ends at 2.5 s; towards ACC the table at h is kept)."""
    hc = round(h + frac * (h2 - h), 2)
    al = tuple(int(np.floor(x)) for x in alloc)
    m_lo = metric(t, h, al, hc)
    if t.contract == "B" and h2 >= P.H_ACC - 1e-9:
        return m_lo
    m_hi = metric(t, h2, al, hc)
    if not (np.isfinite(m_lo) and np.isfinite(m_hi)):
        return np.inf
    return m_lo + frac * (m_hi - m_lo)


def frozen_metrics(t, pl, policy, n_pts=6, split=False):
    """Worst instantaneous contracted metric over the whole maneuver and, if
    split, also over the deficit steps only (steps in which the lender holds
    less than the reservation of its start gap at some instant: the loan
    steps of LTR, every releasing step of graduated release and naive
    preemption, none for wait-for-maneuver). Returns worst or
    (worst, worst_deficit, n_deficit_steps)."""
    st, phis = pl["steps"], pl.get("phis", [])
    worst = worst_d = 0.0
    n_def = 0
    fl = flags_of(t)
    for j in range(len(st)):
        h, h2 = st[j][0], st[j][1]
        full = per_link(t.contract, h, t.beta, fl, t.eta)
        w_step, deficit_step = 0.0, False
        for frac in np.linspace(0.0, 1.0, n_pts):
            al = alloc_at(t, st, phis, policy, j, frac)
            if any(np.floor(x) < y for x, y in zip(al, full)):
                deficit_step = True
            w_step = max(w_step, inst_metric(t, h, h2, al, frac))
        worst = max(worst, w_step)
        if deficit_step:
            n_def += 1
            worst_d = max(worst_d, w_step)
    return (worst, worst_d, n_def) if split else worst


# ---------------------------------------------------------------- service
def service(events, free, D, tgrid):
    """Share of the surge D served over time."""
    served = np.where(tgrid >= T_S, min(free, D), 0.0)
    for (te, x) in events:
        served += np.where(tgrid >= te, x, 0.0)
    return np.minimum(served, D) / D


def service_metrics(sc, tgrid):
    def first(th):
        ok = sc >= th - 1e-9
        return float(tgrid[np.argmax(ok)] - T_S) if np.any(ok) else np.inf
    win = (tgrid >= T_S) & (tgrid < T_S + 10)
    return dict(t50=first(0.5), t95=first(0.95), t_full=first(1.0),
                unserved10=float(np.mean(1 - sc[win])))
