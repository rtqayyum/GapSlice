"""Local velocity observer plus a separately justified acceleration lower bound.

The ESO supplies a nominal predictor, not a safety theorem. The finite-window
lower bound follows from bounded velocity-measurement error and a one-sided
jerk bound, independently of ESO convergence or wireless delivery.
"""
from collections import deque
import numpy as np

from gapslice.certified.safety import down,up


class Observer:
    def __init__(self,shape,bounds,window_s=.15,bandwidth=8.):
        self.b=bounds;self.window=max(1,round(window_s/bounds.control_s))
        self.omega=bandwidth;self.history=deque(maxlen=self.window+1)
        self.velocity=None;self.acceleration=np.zeros(shape);self.jerk=np.zeros(shape)
        self.lower=np.full(shape,-bounds.brake)

    def update(self,pred_velocity_measurement):
        b=self.b;dt=b.control_s;y=np.asarray(pred_velocity_measurement)
        if self.velocity is None:self.velocity=y.copy()
        innovation=y-self.velocity;w=self.omega
        self.velocity+=dt*(self.acceleration+3*w*innovation)
        self.acceleration=np.clip(self.acceleration+dt*(self.jerk+3*w*w*innovation),-b.brake,b.acceleration_max)
        self.jerk=np.clip(self.jerk+dt*w**3*innovation,-b.actual_jerk_bound,b.actual_jerk_bound)
        self.lower=np.maximum(-b.brake,down(self.lower-up(b.actual_jerk_bound*dt)))
        self.history.append(y.copy())
        if len(self.history)==self.window+1:
            duration=self.window*dt
            # The difference quotient can overestimate past-average acceleration
            # by at most 2*eps/duration. A lower jerk bound relates that average
            # to current effective acceleration, including an upward stop jump.
            average=down(down(y-self.history[0])/duration)
            error=up(up(2*up(b.own_speed_error_mps+b.relative_speed_error_mps))/duration)
            drift=up(.5*up(b.actual_jerk_bound*duration))
            measured_lower=down(down(average-error)-drift)
            self.lower=np.maximum(self.lower,np.maximum(-b.brake,measured_lower))
        return self.lower

    def feedforward(self,packet,age,mode='fused'):
        prediction=np.clip(self.acceleration,-self.b.brake,self.b.acceleration_max)
        if mode=='radar':return prediction
        if mode=='hold':return np.where(age<=5/30,packet,0.)
        if mode!='fused':raise ValueError('Unknown predictor mode')
        weight=np.exp(-np.minimum(age,100.)/.06)
        extrapolated=np.clip(packet+np.minimum(age,.15)*self.jerk,-self.b.brake,self.b.acceleration_max)
        result=weight*extrapolated+(1-weight)*prediction
        # Nominal fusion clamp only: a stop can create an upward effective-a
        # jump outside a symmetric jerk interval. Safety uses the separately
        # valid one-sided lower bound, never this nominal clipping interval.
        radius=self.b.actual_jerk_bound*age+self.b.own_acceleration_error_mps2
        return np.clip(result,np.maximum(-self.b.brake,packet-radius),np.minimum(self.b.acceleration_max,packet+radius))
