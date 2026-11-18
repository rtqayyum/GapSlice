"""Finite-family risk tests, using standard fixed-sequence/Learn-then-Test ideas.

The independent sampling unit is a complete maneuver episode, not a packet.
Episodes must be iid within each declared environment. Packets, links and
copies within an episode can be dependent. A design-derived order must be
frozen before inspecting calibration outcomes. This is not a new statistical
theorem, a guarantee under distribution shift, or a dependent-stream test.
"""
import hashlib
import json
import math

from scipy.stats import beta, binom


def validate_count(failures, episodes):
    if (not isinstance(episodes, int) or not isinstance(failures, int)
            or episodes < 1 or not 0 <= failures <= episodes):
        raise ValueError('Require integer counts with 0 <= failures <= episodes and episodes > 0')


def upper_bound(failures, episodes, alpha=.05):
    """One-sided exact binomial (Clopper-Pearson) upper confidence bound."""
    validate_count(failures, episodes)
    if not 0 < alpha < 1:
        raise ValueError('alpha must be in (0,1)')
    return 1. if failures == episodes else float(beta.ppf(1-alpha, failures+1, episodes-failures))


def minimum_zero_failure_episodes(delta, alpha):
    if not 0 < delta < 1 or not 0 < alpha < 1:
        raise ValueError('delta and alpha must be in (0,1)')
    return math.ceil(math.log(alpha)/math.log1p(-delta))


def certify(order, counts, delta=.01, alpha=.05, procedure='fixed_sequence', risk_targets=None):
    """Return a risk-qualified subset; do not use test-set counts here.

    counts[profile_id][environment] = {failures: int, episodes: int}.
    The max p-value is an intersection-union test: an accepted profile must
    pass in every declared environment. Fixed sequence stops at the first
    failure, even if a later profile would pass. Bonferroni tests all profiles
    at alpha/M. Arbitrary dependence across profile test statistics is allowed.
    Across separate calls/chains, the caller must allocate a global alpha.
    """
    if not order or len(set(order)) != len(order) or set(order) != set(counts):
        raise ValueError('Order must contain each predeclared profile exactly once')
    if not 0 < delta < 1 or not 0 < alpha < 1:
        raise ValueError('delta and alpha must be in (0,1)')
    if risk_targets is not None and (set(risk_targets)!=set(order) or
                                      any(not 0 < v < 1 for v in risk_targets.values())):
        raise ValueError('Every hypothesis needs a valid predeclared risk target')
    if procedure not in {'fixed_sequence', 'bonferroni'}:
        raise ValueError('Unknown risk-testing procedure')
    domains=set(counts[order[0]])
    if not domains or any(set(counts[k]) != domains for k in order):
        raise ValueError('Every profile must cover the same nonempty environment set')
    level=alpha if procedure == 'fixed_sequence' else alpha/len(order)
    accepted, tested=[], []
    for key in order:
        target=delta if risk_targets is None else risk_targets[key]
        details={}
        for env, c in sorted(counts[key].items()):
            validate_count(c['failures'], c['episodes'])
            details[env]=dict(**c, p_value=float(binom.cdf(c['failures'], c['episodes'], target)),
                             upper_risk=upper_bound(c['failures'], c['episodes'], level))
        p_value=max(v['p_value'] for v in details.values())
        passes=p_value <= level
        tested.append(dict(profile=key, risk_target=target, p_value=p_value, accepted=passes, environments=details))
        if passes:
            accepted.append(key)
        elif procedure == 'fixed_sequence':
            break
    order_hash=hashlib.sha256(json.dumps(order,separators=(',',':')).encode()).hexdigest()
    return dict(procedure=procedure, alpha_chain=alpha, per_test_alpha=level, delta=delta,
                order=order, order_sha256=order_hash, risk_targets=risk_targets, accepted=accepted, tested=tested,
                untested=[k for k in order if k not in {t['profile'] for t in tested}],
                scope='Finite-horizon episode risk in declared iid environment populations; not physical safety certification')
