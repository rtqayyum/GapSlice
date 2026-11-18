"""Independent numerical falsification checks supporting the analytic proof.

These tests are evidence against implementation errors, not replacements for
universal mathematical arguments. Reference integration never calls envelopes.
"""
from dataclasses import asdict
from decimal import Decimal,localcontext
import math

import numpy as np
from scipy.integrate import solve_ivp

from gapslice.certified.safety import Bounds,Shield,exp_integral_bounds
from gapslice.certified.simulator import plant_step
from gapslice.certified.risk import nominal_certificate


def verify(path,cases=128):
    with Shield(path) as shield:return _verify(shield,cases)


def _verify(shield,cases):
    b=shield.bounds;rng=np.random.default_rng(90927)
    # Decimal exp at 80 digits is independent of the alternating Taylor code.
    checked=0
    with localcontext() as context:
        context.prec=80
        for h in [b.control_s,b.envelope_s]:
            for eta in [b.eta_min,b.eta_max]:
                c5,c3=exp_integral_bounds(h,eta)
                e=(-Decimal(h)/Decimal(eta)).exp();integral=Decimal(eta)*(1-e)
                for (lo,hi),reference in [(c5,e),(c3,integral)]:
                    if not Decimal(lo)<=reference<=Decimal(hi):raise AssertionError('Interval exponential failed')
                    checked+=1
    # Verify continuous-lag integration independently with high-accuracy RK45,
    # including zero-speed holds/restarts (small-step projected reference).
    qerr=verr=aerr=0.
    for v,a,u,eta,t in [(17.,.7,-6.,.25,.7),(1.,-3.,-6.,.45,.08),(0.,-1.,2.,.3,1.)]:
        initial=[0.,v,a]
        def rhs(_,x):return [max(0.,x[1]),x[2] if x[1]>0 or x[2]>0 else 0.,(u-x[2])/eta]
        ref=solve_ivp(rhs,[0,t],initial,rtol=2e-11,atol=2e-12,max_step=1e-3).y[:,-1]
        actual=plant_step(*[np.array([z]) for z in [0.,v,a,u,eta]],t)
        errors=np.abs(np.array([x[0] for x in actual])-ref)
        qerr=max(qerr,float(errors[0]));verr=max(verr,float(errors[1]));aerr=max(aerr,float(errors[2]))
    if max(qerr,verr,aerr)>2e-6:raise AssertionError('Independent plant integration mismatch')
    # Adversarial fallback: predecessor begins at maximum physical braking,
    # which is worse than acceleration-memory estimates at entry. Ego commands
    # rise maximally for the whole admissible prefix then brake maximally.
    # Sample full supported speeds, accelerations, command states and lag range.
    n=cases;dt=.002;count=round(12/dt)
    v=rng.uniform(0,b.maximum_speed,n);a=rng.uniform(-b.brake,b.acceleration_max,n)
    u=rng.uniform(-b.brake,b.acceleration_max,n);pv=rng.uniform(0,b.maximum_speed,n)
    # Actual jerk condition only needed for predecessor, who is already braking.
    eta=rng.choice([b.eta_min,b.eta_max],n);margins=[]
    for prefix in [False,True]:
        required,valid=shield.required_clearance(v,a,u,pv,np.full(n,-b.brake),prefix)
        if not np.all(valid):raise AssertionError('Valid table states rejected')
        x=np.zeros(n);vv=v.copy();aa=a.copy();uu=u.copy();px=np.zeros(n);pvv=pv.copy()
        maximum=np.zeros(n)
        for tick in range(count):
            t=tick*dt
            if tick%round(b.control_s/dt)==0:
                step=(1 if prefix and t<b.guard_s-1e-10 else -1)*b.command_jerk*b.control_s
                uu=np.clip(uu+step,-b.brake,b.acceleration_max)
            x,vv,aa=plant_step(x,vv,aa,uu,eta,dt)
            nextpv=np.maximum(0.,pvv-b.brake*dt)
            # Exact constant braking to zero, not an envelope recurrence.
            time=np.minimum(dt,pvv/b.brake);px+=pvv*time-.5*b.brake*time*time;pvv=nextpv
            maximum=np.maximum(maximum,x-px)
        margin=required-b.minimum_clearance_m-maximum
        if np.min(margin)<-1e-8:raise AssertionError('Braking envelope was falsified')
        margins.append(float(np.min(margin)))
    return dict(status='passed',bounds=asdict(b),table_id=b.key,decimal_interval_checks=checked,
        independent_integrator_max_errors=dict(position=qerr,velocity=verr,acceleration=aerr),
        adversarial_cases=2*n,minimum_envelope_slack_m=min(margins),
        nominal=nominal_certificate(.8,1.8),
        scope='Numerical falsification and algebraic witness checks supporting the conditional analytic arguments; not a machine-checked theorem or testbed validation')
