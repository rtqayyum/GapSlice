"""Radio side of GapSlice: SINR of a predecessor-follower sidelink under
Mode-1 reuse, finite-blocklength delivery probability with HARQ attempts,
and the PRB requirement for a target per-period delivery probability."""
import numpy as np
from functools import lru_cache
from scipy.stats import norm, ncx2, chi2
from gapslice import params as P
LOG2E = np.log2(np.e)


def pathloss_db(d, fc=P.FC_GHZ):
    """3GPP TR 37.885 highway LOS path loss."""
    return 32.4 + 20 * np.log10(d) + 20 * np.log10(fc)


def mean_sinr_db(h, blocked=False, reuse_d=P.REUSE_D, n_int=P.N_INTERF,
                 ptx_dbm=23.0, g_ant_db=3.0, nf_db=9.0, ref_prbs=10):
    d = P.antenna_distance(h)
    eirp = ptx_dbm + 2 * g_ant_db
    s = eirp - pathloss_db(d) - (P.BLOCK_MU_DB if blocked else 0.0)
    i_lin = n_int * 10 ** ((eirp - pathloss_db(reuse_d)) / 10)
    n_lin = 10 ** ((-174 + 10 * np.log10(ref_prbs * 12 * 30e3) + nf_db) / 10)
    return s - 10 * np.log10(i_lin + n_lin)


def design_sinr_db(h, blocked=False, eps=P.EPS_LINK_REF, **kw):
    """eps-quantile of the large-scale SINR of one link (eps = per-link outage
    share; P.eps_link(L) for a platoon with L links)."""
    sig = P.SIGMA_LS_DB if not blocked else np.hypot(P.SIGMA_LS_DB, P.BLOCK_SIGMA_DB)
    return mean_sinr_db(h, blocked, **kw) - norm.ppf(1 - eps) * sig


def fbl_error(n, snr_lin, L=P.PAYLOAD_BITS):
    """Normal approximation (Polyanskiy-Poor-Verdu) with an MCS cap."""
    snr_lin = np.asarray(snr_lin, dtype=float)
    if L / n > P.SE_MAX:
        return np.ones_like(snr_lin)
    C = np.log2(1 + snr_lin)
    V = (1 - (1 + snr_lin) ** -2) * LOG2E ** 2
    arg = (n * C - L + 0.5 * np.log2(n)) / np.sqrt(np.maximum(n * V, 1e-30))
    return norm.sf(arg)


@lru_cache(maxsize=8)
def _fading_grid(rice_k_db, n_rx, npts=6000):
    """Grid over the normalized fading power x (mean n_rx) with cell probs."""
    x = np.logspace(-7, np.log10(60.0 * n_rx), npts)
    if np.isinf(rice_k_db) and rice_k_db < 0:
        cdf = chi2.cdf(2 * x, df=2 * n_rx)
    else:
        K = 10 ** (rice_k_db / 10)
        cdf = ncx2.cdf(2 * (K + 1) * x, df=2 * n_rx, nc=2 * K * n_rx)
    probs = np.diff(np.concatenate([[0.0], cdf]))
    tail = 1.0 - cdf[-1]
    xm = x.copy()  # right-endpoint rule is conservative for decreasing eps(x)
    xm[0] = 0.0
    return xm, probs, tail


def attempt_error(n, sinr_db, rice_k_db=P.RICE_K_DB, n_rx=P.N_RX, L=None):
    L = P.PAYLOAD_BITS if L is None else L
    x, w, tail = _fading_grid(rice_k_db, n_rx)
    g = 10 ** (sinr_db / 10)
    # left endpoint for each cell: conservative (eps decreasing in x)
    xl = np.concatenate([[0.0], x[:-1]])
    return float(np.sum(w * fbl_error(n, g * xl, L)))


def delivery_prob(b, m, sinr_db, **kw):
    """Per-period delivery probability with b PRBs per attempt, m attempts."""
    e = attempt_error(b * P.N_RE_PRB, sinr_db, **kw)
    return 1.0 - e ** m


def prbs_for_target(p_target, sinr_db, m_max=P.M_MAX, **kw):
    """Minimum total PRBs (m*b) achieving p_target; returns (total, m, b).
    inf if infeasible. Optional kw: rice_k_db, n_rx, L (payload bits)."""
    if not np.isfinite(p_target):
        return np.inf, 0, 0
    if p_target <= 0.0:
        return 0, 0, 0
    best = (np.inf, 0, 0)
    L = kw.get("L") or P.PAYLOAD_BITS
    b_min = int(np.ceil(L / (P.SE_MAX * P.N_RE_PRB)))
    for m in range(1, m_max + 1):
        if delivery_prob(P.B_MAX, m, sinr_db, **kw) < p_target:
            continue
        lo, hi = b_min, P.B_MAX
        if delivery_prob(lo, m, sinr_db, **kw) >= p_target:
            hi = lo
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if delivery_prob(mid, m, sinr_db, **kw) >= p_target:
                hi = mid
            else:
                lo = mid
        if m * hi < best[0]:
            best = (m * hi, m, hi)
    return best


def prob_from_prbs(total_prbs, sinr_db, m_max=P.M_MAX, **kw):
    """Best delivery probability obtainable with a PRB budget (split m x b)."""
    best = 0.0
    for m in range(1, m_max + 1):
        b = int(total_prbs // m)
        if b < 1:
            continue
        best = max(best, delivery_prob(b, m, sinr_db, **kw))
    return best
