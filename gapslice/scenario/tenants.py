"""Tenant (platoon) population and per-gap option menus.

Menu kinds:
  "ceb"  : control-effective bandwidth (type A: string water-filling of the
           certified gain budget; type B: per-event descriptor for N trucks)
  "tier" : outcome-matched reliability classes: every link receives the
           smallest class in {90, 99, 99.9, 99.99, 99.999} % that meets the
           same contract with a per-vehicle split of the budget
"""
import numpy as np
from functools import lru_cache
from gapslice import params as P
from gapslice.descriptor.tables import p_c, p_tail
from gapslice.allocation.ceb import waterfill, urllc_link, ceb_tail_platoon, class_link, link_prbs
from gapslice.channel.link import design_sinr_db

H_OFFER = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5,
           1.75, 2.0, 2.25, 2.5]


def fuel_saving(h):
    """Illustrative follower fuel saving vs time gap (decreasing, convex)."""
    return 0.15 * np.exp(-h / 0.8) + 0.01


@lru_cache(maxsize=None)
def _ceb_A(h, beta, n_blocked, L, eta):
    flags = tuple([True] * n_blocked + [False] * (L - n_blocked))
    b, gams = waterfill(h, beta, flags, P.GAMMA_LINK ** L, eta)
    return float(b), (None if gams is None else tuple(gams))


@lru_cache(maxsize=None)
def _ceb_B(h, beta, n_blocked, L, eta):
    flags = tuple([True] * n_blocked + [False] * (L - n_blocked))
    return float(ceb_tail_platoon(h, beta, flags, eta, N=L + 1))


@lru_cache(maxsize=None)
def _tier(h, beta, n_blocked, L, eta, contract):
    pc = p_c(h, beta, P.GAMMA_LINK, eta) if contract == "A" else p_tail(h, beta, eta, L + 1)
    flags = [True] * n_blocked + [False] * (L - n_blocked)
    return float(sum(class_link(h, pc, bf, P.eps_link(L)) for bf in flags))


class Tenant:
    def __init__(self, k, N, eta, beta, blocked, w, contract="A"):
        self.k, self.N, self.eta, self.beta = k, N, eta, beta
        self.contract = contract
        self.blocked = tuple(bool(b) for b in blocked)
        self.nb = int(sum(self.blocked))
        self.w = w
        self.L = N - 1
        self.gamma_h2t = P.GAMMA_LINK ** self.L
        self._menus = {}

    def U(self, h):
        return self.w * self.L * fuel_saving(h)

    def demand(self, h, kind="ceb"):
        if h >= P.H_ACC - 1e-9:
            return 0.0
        if kind == "ceb":
            if self.contract == "A":
                return _ceb_A(h, self.beta, self.nb, self.L, self.eta)[0]
            return _ceb_B(h, self.beta, self.nb, self.L, self.eta)
        return _tier(h, self.beta, self.nb, self.L, self.eta, self.contract)

    def gammas(self, h):
        """Per-link gain split chosen by water-filling (blocked links first)."""
        return _ceb_A(h, self.beta, self.nb, self.L, self.eta)[1]

    def menu(self, kind="ceb"):
        """Options [(h, b, U)] sorted by h, ending with ACC (b=0); only
        Pareto options (b strictly decreasing with h) are kept."""
        if kind not in self._menus:
            opts = []
            for h in H_OFFER:
                b = self.demand(h, kind)
                if np.isfinite(b):
                    opts.append((h, float(b), self.U(h)))
            opts.append((P.H_ACC, 0.0, self.U(P.H_ACC)))
            pareto, best_b = [], np.inf
            for o in sorted(opts, key=lambda o: o[0]):
                if o[1] < best_b - 1e-9:
                    pareto.append(o); best_b = o[1]
            self._menus[kind] = pareto
        return self._menus[kind]

    def h_pref_urllc(self):
        """Smallest offered gap that a 99.99 % link SLA actually meets for
        this tenant's contract (so the 99.99 % baseline is not knowingly
        below the outcome)."""
        for h in H_OFFER:
            pc = p_c(h, self.beta, P.GAMMA_LINK, self.eta) if self.contract == "A" \
                else p_tail(h, self.beta, self.eta, self.N)
            if np.isfinite(pc) and pc <= P.P_URLLC:
                return h
        return P.H_ACC

    def urllc_demand(self, h):
        if h >= P.H_ACC:
            return 0.0
        return float(sum(urllc_link(h, bf, eps=P.eps_link(self.L)) for bf in self.blocked))


def draw_tenants(n, seed, contract="A"):
    rng = np.random.default_rng(seed)
    T = []
    for k in range(n):
        N = int(rng.integers(3, 8))
        eta = float(rng.choice([0.3, 0.4]))
        beta = float(rng.choice([0.0, 2.0, 4.0], p=[0.3, 0.5, 0.2]))
        blocked = rng.random(N - 1) < 0.2
        w = float(rng.uniform(0.5, 1.5))
        T.append(Tenant(k, N, eta, beta, blocked, w, contract))
    return T


def flags_of(t):
    """Blocked-link flags of a tenant's platoon, blocked links first. Per-link
    reservations are stored in this order."""
    return tuple(sorted(t.blocked, reverse=True))
