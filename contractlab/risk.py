"""Simultaneous qualification; no arbitrary minimum one-sixteenth risk label.

The CP root is proposed numerically and rounded UP to a probability grid.
Decimal directed interval arithmetic then verifies the defining binomial-tail
inequality. A label is never admitted solely because SciPy returned a number.
"""
from decimal import Decimal, localcontext, ROUND_CEILING, ROUND_FLOOR
from functools import lru_cache
import math
from scipy.stats import beta

SCALE = 1_000_000


def tail_upper(k, n, units):
    if not 0 <= k < n or not 0 < units < SCALE: raise ValueError('Invalid tail')
    # P[X<=k] = (1-p)^n * sum_{j=0}^k C(n,j)(p/(1-p))^j.
    # Every operand is nonnegative; every operation rounds toward +infinity.
    with localcontext() as ctx:
        ctx.prec=60;ctx.rounding=ROUND_CEILING
        p=Decimal(units)/SCALE; q=Decimal(SCALE-units)/SCALE
        term=q**n; total=term
        for j in range(k):
            term=term*Decimal(n-j)/Decimal(j+1)*p/q
            total+=term
        return +total


@lru_cache(maxsize=100000)
def upper_units(k, n, tests, alpha_numerator=1, alpha_denominator=40):
    if type(k) is not int or type(n) is not int or not 0<=k<=n or n<1 or tests<1:
        raise ValueError('Invalid Bernoulli counts/family')
    if k==n:return SCALE
    alpha=alpha_numerator/(alpha_denominator*tests)
    with localcontext() as ctx:
        ctx.prec=60;ctx.rounding=ROUND_FLOOR
        threshold=Decimal(alpha_numerator)/Decimal(alpha_denominator*tests)
    proposed=float(beta.ppf(1-alpha,k+1,n-k))
    if not math.isfinite(proposed):return SCALE
    units=max(1,math.ceil(proposed*SCALE)+1)
    while units<SCALE and tail_upper(k,n,units)>threshold:units+=1
    return min(units,SCALE)


def qualify(failures, episodes, reward_sum, maximum_reward, family):
    risk=upper_units(int(failures),int(episodes),int(family))
    # Rewards lie in [0,h_initial-h_target]; disjoint benefit confidence budget.
    radius=maximum_reward*math.sqrt(math.log(40*family)/(2*episodes))
    lower=max(0.,reward_sum/episodes-radius)
    return dict(risk_units=risk,risk_upper=risk/SCALE,
                benefit_microseconds=math.floor(lower*1e6),benefit_lower_s=lower,
                risk_family_alpha=.025,benefit_family_alpha=.025,
                family_size=family,episodes=episodes,failures=failures)


def deployment_allowed(contract, context, horizon_s, payload, fingerprint):
    """Metadata check only; hardware bounds/initial backup need separate checks.

    A new context/horizon/payload needs new qualification. A true value alone
    is NOT a production deployment authorization or physical safety certificate.
    """
    return (contract['context']==context and contract['horizon_s']==horizon_s and
            contract['profile']['payload_bytes']==payload and
            contract['source_sha256']==fingerprint and contract['qualified'])
