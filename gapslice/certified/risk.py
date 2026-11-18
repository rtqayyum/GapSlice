"""Finite-family exact binomial qualification, independent of design selection."""
from fractions import Fraction
from functools import lru_cache
import math

import numpy as np
from scipy.stats import beta


RISK_DENOMINATOR=1600
RISK_UNITS=(1,2,4,8,16)
FLEET_UNITS=16


@lru_cache(maxsize=64)
def critical_count(n,risk_units,tests):
    """Largest k with P[Bin(n, units/1600)<=k] <= 1/(25*tests).

    All acceptance decisions use Python integers, not floating binomial tails.
    The recursion is exact because each term is an integer binomial numerator.
    The test is monotone in the number of observed failures.
    """
    if any(type(x) is not int or x<=0 for x in [n,risk_units,tests]) or risk_units>=RISK_DENOMINATOR:
        raise ValueError('Positive integer sample size, risk units and test count required')
    f=Fraction(risk_units,RISK_DENOMINATOR);a=f.numerator;b=f.denominator
    denominator=pow(b,n);term=pow(b-a,n);cumulative=term;level_denominator=25*tests
    if cumulative*level_denominator>denominator:return -1
    accepted=0
    # A binomial median is at least floor(n*p), so this reaches a rejecting
    # count for levels below .04; retain an explicit check rather than assume.
    cap=min(n,math.ceil(n*a/b)+1)
    for k in range(1,cap+1):
        numerator=term*(n-k+1)*a;divisor=k*(b-a)
        term,remainder=divmod(numerator,divisor)
        if remainder:raise ArithmeticError('Nonintegral binomial recursion')
        cumulative+=term
        if cumulative*level_denominator>denominator:return accepted
        accepted=k
    raise ArithmeticError('No rejecting binomial count found')


def qualify(failures,n,tests):
    if not isinstance(failures,int) or not 0<=failures<=n:raise ValueError('Invalid failure count')
    return [u for u in RISK_UNITS if failures<=critical_count(n,u,tests)]


def benefit_lower(total,n,maximum,tests):
    """Hoeffding LCB, family failure <=.01 over the declared finite family.

    Inputs are finite, success-gated nonnegative episode rewards <= maximum.
    A small conservative numerical margin protects this non-formal float LCB;
    exact risk acceptance above does not depend on this calculation.
    """
    if n<=0 or tests<1 or maximum<0 or not 0<=total<=n*maximum+1e-8:raise ValueError('Invalid bounded reward')
    penalty=maximum*math.sqrt(math.log(100*tests)/(2*n))
    return max(0.,total/n-penalty-1e-10*max(1.,maximum))


def cp_upper(k,n,alpha=.05):
    """Descriptive single-cell Clopper-Pearson bound, not selection qualification."""
    return 1. if k==n else float(beta.ppf(1-alpha,k+1,n-k))


def nominal_certificate(kp,kd):
    """Algebraic Lyapunov witness for ideal e''+kd e'+kp e=Delta."""
    if not math.isfinite(kp+kd) or min(kp,kd)<=0:raise ValueError('Positive finite gains required')
    p=np.array([[kd/(2*kp)+(kp+1)/(2*kd),1/(2*kp)],
                [1/(2*kp),(kp+1)/(2*kp*kd)]])
    a=np.array([[0.,1.],[-kp,-kd]])
    residual=float(np.max(np.abs(a.T@p+p@a+np.eye(2))))
    eigen=np.linalg.eigvalsh(p)
    if residual>1e-10 or eigen[0]<=0:raise ArithmeticError('Lyapunov witness rejected')
    return dict(P=p.tolist(),lambda_min=float(eigen[0]),lambda_max=float(eigen[-1]),
        residual=residual,iss_rate=1/(2*float(eigen[-1])),
        disturbance_coefficient=2*float(np.sum(p[:,1]**2)),
        scope='Ideal unsaturated continuous-time computed-input error dynamics; residual disturbance includes sensing, lag mismatch, sampling and clipping. Not string stability.')
