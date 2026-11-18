"""Independent physical replay for assumption-conditional safety certificates.

All compared controllers use the same plant, bounded sensors and physical
command limits. These differ explicitly from Guard v1; do not claim a matched
improvement over v1's Gaussian sensors/2.5-only jerk model. The normal-approximate
radio remains a surrogate and is separately labeled.
"""
from dataclasses import asdict,dataclass
import hashlib
import math

import numpy as np

from gapslice.certified.observer import Observer
from gapslice.certified.profiles import Profile
from gapslice.certified.safety import Bounds,Shield,down,up
from gapslice.guard.phy import decode_error,transport
from gapslice.guard.simulator import ENVIRONMENTS


@dataclass(frozen=True)
class Policy:
    controller:str='fused'
    kp:float=.8
    kd:float=1.8
    observer_bandwidth:float=8.
    reference_rate:float=.15
    reference_acceleration:float=.08
    comfort_jerk:float=2.5
    shield:bool=True

    def check(self):
        if (self.controller not in {'fused','hold','radar'} or min(self.kp,self.kd,self.observer_bandwidth,
                self.reference_rate,self.reference_acceleration,self.comfort_jerk)<=0 or self.comfort_jerk>8):
            raise ValueError('Invalid controller policy')


@dataclass(frozen=True)
class Model:
    horizon_s:float=40.
    dt_s:float=.002
    control_s:float=.01
    ramp_start_s:float=2.
    tracking_limit_m:float=5.
    completion_tolerance_s:float=.01
    standstill_m:float=2.
    truck_length_m:float=16.5
    initial_speed_mps:float=80/3.6
    eta_nominal:float=.35
    eta_mode:str='uniform'
    brake_mode:str='random'
    radio_mode:str='surrogate'
    data_namespace:str='cert-development-v1'


def rng(seed,split,component,namespace):
    if split not in {'design','calibration','test','verification'}:raise ValueError('Invalid data split')
    payload=f'GapSlice-Cert/{namespace}/{seed}/{split}/{component}'.encode()
    return np.random.default_rng(np.random.SeedSequence(np.frombuffer(hashlib.sha256(payload).digest(),dtype='<u4')))


def coefficients(dt,eta):
    c5=np.exp(-dt/eta);c6=1-c5;c3=eta*c6;c4=dt-c3
    c1=eta*(dt-eta*c6);c2=dt*dt/2-c1
    return c1,c2,c3,c4,c5,c6


def plant_step(position,velocity,acceleration,command,eta,dt):
    """Exact ZOH integration, resolving zero-speed stops and restarts.

    The safety-table builder does not call this function. The effective
    kinematic acceleration is zero while stopped with negative drivetrain a.
    """
    c1,c2,c3,c4,c5,c6=coefficients(dt,eta)
    displacement=dt*velocity+c1*acceleration+c2*command
    v_end=velocity+c3*acceleration+c4*command
    a_end=c5*acceleration+c6*command
    # A velocity minimum can occur where a rises through zero.
    rising=(acceleration<0)&(command>0)
    zero_a=np.full_like(velocity,np.inf)
    zero_a[rising]=eta[rising]*np.log((command[rising]-acceleration[rising])/command[rising])
    t_min=np.minimum(zero_a,dt)
    _,_,c3m,c4m,_,_=coefficients(t_min,eta)
    v_min=velocity+c3m*acceleration+c4m*command
    stopped=v_min<0
    if np.any(stopped):
        v0=velocity[stopped];a0=acceleration[stopped];u=command[stopped];tau=eta[stopped]
        lo=np.zeros_like(v0);hi=t_min[stopped].copy()
        for _ in range(32):
            mid=(lo+hi)/2;_,_,c3x,c4x,_,_=coefficients(mid,tau)
            positive=v0+c3x*a0+c4x*u>0
            lo=np.where(positive,mid,lo);hi=np.where(positive,hi,mid)
        stop=(lo+hi)/2;c1x,c2x,_,_,_,_=coefficients(stop,tau)
        qstop=stop*v0+c1x*a0+c2x*u
        restart=np.maximum(0.,dt-zero_a[stopped])
        _,c2r,_,c4r,_,_=coefficients(restart,tau)
        displacement[stopped]=qstop+c2r*u
        v_end[stopped]=c4r*u
    return position+np.maximum(displacement,0.),np.maximum(v_end,0.),a_end


def repeat_factor(profile,environment):
    if profile.copies==0:return np.broadcast_to(np.eye(4),(profile.n_trucks-1,4,4)).copy()
    result=[];relative=profile.relative()
    for link in range(profile.n_trucks-1):
        pp=[x for x in relative if x[0]==link]
        times=[x[2]*profile.slot_s for x in pp];freq=[x[3] for x in pp]
        while len(times)<4:times.append(times[-1]+profile.slot_s);freq.append(freq[-1])
        cov=np.exp(-np.abs(np.subtract.outer(times,times))/environment.coherence_s-
                   np.abs(np.subtract.outer(freq,freq))/environment.coherence_prbs)
        result.append(np.linalg.cholesky(cov+1e-12*np.eye(4)))
    return np.asarray(result)


def simulate(profile,policy,environment,seed,episodes,split,tables,model=None,verify_table_hashes=False):
    if not isinstance(tables,Shield):
        with Shield(tables,verify_hashes=verify_table_hashes) as shield:
            return simulate(profile,policy,environment,seed,episodes,split,shield,model)
    profile.check();policy.check();model=Model() if model is None else model
    shield=tables
    b=shield.bounds
    if (model.control_s!=b.control_s or not math.isclose(model.control_s/model.dt_s,round(model.control_s/model.dt_s))
            or not math.isclose(b.guard_s/model.control_s,round(b.guard_s/model.control_s))
            or model.radio_mode not in {'surrogate','perfect','absent'}):raise ValueError('Inconsistent integration/control/proof clocks')
    if episodes<1 or model.horizon_s<=model.ramp_start_s+profile.ramp_s:raise ValueError('Invalid replay extent')
    r=episodes;n=profile.n_trucks;links=n-1;dt=model.dt_s;dc=model.control_s
    def generator(name):return rng(seed,split,name,model.data_namespace)
    # Separate streams per initial plant quantity avoid within-initialization
    # offsets. Full trajectory pairing still requires identical batch sizes,
    # source phase and dimensions; matched controls use those exact settings.
    eta=generator('eta').uniform(b.eta_min,b.eta_max,(r,n))
    if model.eta_mode=='slow':eta[:]=b.eta_max
    elif model.eta_mode=='alternating':eta[:,::2]=b.eta_min;eta[:,1::2]=b.eta_max
    elif model.eta_mode!='uniform':raise ValueError('Unknown actuator stress model')
    velocity=model.initial_speed_mps+generator('initial_velocity').uniform(-.15,.15,(r,n))
    acceleration=generator('initial_acceleration').uniform(-.05,.05,(r,n));command=np.zeros((r,n))
    initial_post_error=(np.abs(command-acceleration)+b.command_jerk*dc)/eta
    invariant=b.command_jerk*dc/(eta*(-np.expm1(-dc/eta)))
    if np.any(initial_post_error>invariant):raise ValueError('Initial actuator mismatch does not satisfy jerk invariant')
    position=np.zeros((r,n));initial_gaps=model.standstill_m+profile.h_initial*velocity[:,1:]+generator('initial_gap').uniform(-.25,.25,(r,links))
    position[:,1:]=-np.cumsum(model.truck_length_m+initial_gaps,axis=1)
    leader_start=generator('leader_start').uniform(3.,8.,r)
    leader_duration=generator('leader_duration').uniform(1.5,2.5,r)
    leader_brake=generator('leader_brake').uniform(-6.,-3.,r)
    if model.brake_mode=='hard':leader_brake[:]=-b.brake
    elif model.brake_mode!='random':raise ValueError('Unknown braking stress model')
    sensor=generator('sensors');fade=generator('fading');decode=generator('decoding');shadow_rng=generator('shadow')
    rho=environment.cross_link_correlation
    shadow=environment.shadow_sigma_db*(np.sqrt(rho)*shadow_rng.standard_normal((r,1))+
                                       np.sqrt(1-rho)*shadow_rng.standard_normal((r,links)))
    if environment.blocked:shadow[:,links//2]+=9+4.5*shadow_rng.standard_normal(r)
    cholesky=repeat_factor(profile,environment);z=np.zeros((r,links,4),dtype=complex)
    packet_a=np.zeros((r,links));packet_u=np.zeros((r,links));packet_stamp=np.full((r,links),-np.inf)
    pending_a=packet_a.copy();pending_u=packet_u.copy();pending_tick=np.full((r,links),-1,dtype=int);pending_stamp=0.
    copy_end=np.zeros((links,profile.copies))
    for link in range(links):
        copy_end[link]=[(x[2]+1)*profile.slot_s+.001 for x in profile.relative() if x[0]==link]
    grant=transport(profile.prbs,profile.payload_bytes) if profile.copies else None
    observer=Observer((r,links),b,bandwidth=policy.observer_bandwidth)
    headway=np.full((r,links),profile.h_initial);headway_rate=np.zeros((r,links))
    hdd=np.zeros((r,links))
    peak_error=np.zeros(r);min_clearance=np.full(r,np.inf);completion_time=np.full(r,np.inf)
    gain=np.zeros(r);effort=np.zeros(r);jerk_energy=np.zeros(r);shield_blocks=np.zeros(r,dtype=int)
    packet_lost=np.zeros(r,dtype=int);packet_trials=0;max_age=np.zeros(r)
    observer_breaches=np.zeros(r,dtype=bool);initial_uncertified=np.zeros(r,dtype=bool);guarantee_breaches=np.zeros(r,dtype=bool)
    certified=np.zeros((r,links),dtype=bool);allow=np.ones((r,links),dtype=bool)
    first_failure=None;control_stride=round(dc/dt);guard_stride=round(b.guard_s/dc)
    steps=round(model.horizon_s/dt)
    for tick in range(steps+1):
        t=tick*dt;arrived=pending_tick==tick
        packet_a=np.where(arrived,pending_a,packet_a);packet_u=np.where(arrived,pending_u,packet_u)
        packet_stamp=np.where(arrived,pending_stamp,packet_stamp)
        clearance=position[:,:-1]-position[:,1:]-model.truck_length_m
        error=clearance-model.standstill_m-headway*velocity[:,1:]
        peak_error=np.maximum(peak_error,np.max(np.abs(error),axis=1));min_clearance=np.minimum(min_clearance,np.min(clearance,axis=1))
        completed=np.all(np.abs(headway-profile.h_target)<=model.completion_tolerance_s,axis=1)
        completion_time=np.where(completed&~np.isfinite(completion_time),t,completion_time)
        actual_headway=(clearance-model.standstill_m)/np.maximum(velocity[:,1:],2.)
        gain+=dt*np.mean(np.clip(profile.h_initial-actual_headway,0,max(0.,profile.h_initial-profile.h_target)),axis=1)
        if np.any(certified):
            guarantee_breaches|=np.any(certified&(clearance<b.minimum_clearance_m-1e-7),axis=1)
        if tick==steps:break
        if tick%control_stride==0:
            control_tick=tick//control_stride
            effective_a=np.where((velocity<=1e-10)&(acceleration<0),0.,acceleration)
            own_v=velocity+sensor.uniform(-b.own_speed_error_mps,b.own_speed_error_mps,(r,n))
            own_a=effective_a+sensor.uniform(-b.own_acceleration_error_mps2,b.own_acceleration_error_mps2,(r,n))
            dv=velocity[:,:-1]-velocity[:,1:]+sensor.uniform(-b.relative_speed_error_mps,b.relative_speed_error_mps,(r,links))
            distance=clearance+sensor.uniform(-b.range_error_m,b.range_error_m,(r,links))
            pred_v=own_v[:,1:]+dv
            pred_a_lower=observer.update(pred_v)
            age=t-packet_stamp;fresh=np.isfinite(age)
            radius=up(b.actual_jerk_bound*np.where(fresh,age,0.))
            packet_lower=np.where(fresh,down(down(packet_a-b.own_acceleration_error_mps2)-radius),-b.brake)
            pred_a_lower=np.maximum(pred_a_lower,np.maximum(-b.brake,packet_lower))
            observer.lower=pred_a_lower
            observer_breaches|=np.any(pred_a_lower>effective_a[:,:-1]+1e-7,axis=1)
            finite_age=np.where(fresh,age,model.horizon_s)
            max_age=np.maximum(max_age,np.max(finite_age,axis=1))
            own_v_hi=np.maximum(0.,up(own_v[:,1:]+b.own_speed_error_mps))
            own_a_hi=np.minimum(b.acceleration_max,up(own_a[:,1:]+b.own_acceleration_error_mps2))
            own_a_hi=np.maximum(own_a_hi,-b.brake)
            pred_v_lo=np.maximum(0.,down(down(own_v[:,1:]-b.own_speed_error_mps)+down(dv-b.relative_speed_error_mps)))
            d_lower=down(distance-b.range_error_m)
            if control_tick==0:
                entry,_=shield.decide(d_lower,own_v_hi,own_a_hi,command[:,1:],pred_v_lo,pred_a_lower,False)
                certified=entry.copy() if policy.shield else np.zeros_like(entry)
                initial_uncertified=np.any(~entry,axis=1)
            if control_tick%guard_stride==0:
                allow,margin=shield.decide(d_lower,own_v_hi,own_a_hi,command[:,1:],pred_v_lo,pred_a_lower,True)
                if policy.shield:
                    certified|=allow;shield_blocks+=np.any(~allow,axis=1)
            estimate=observer.feedforward(packet_a,finite_age,policy.controller)
            estimate=np.clip(estimate,pred_a_lower,b.acceleration_max)
            # Smooth reference acceleration is known to the computed-input law.
            e_meas=distance-model.standstill_m-headway*own_v[:,1:]
            remaining=np.maximum(0.,headway-profile.h_target)
            healthy=((t>=model.ramp_start_s)&(np.abs(e_meas)<1.)&(dv>-1.5)&
                     (own_a[:,1:]>-.75)&(estimate>-.75)&(own_v[:,1:]<model.initial_speed_mps+2.))
            if policy.shield:healthy&=allow
            desired_rate=-np.minimum(policy.reference_rate,np.sqrt(2*policy.reference_acceleration*remaining))*healthy
            hdd=np.clip((desired_rate-headway_rate)/.25,-policy.reference_acceleration,policy.reference_acceleration)
            edot=dv-headway*own_a[:,1:]-headway_rate*own_v[:,1:]
            requested=own_a[:,1:]+model.eta_nominal/headway*(estimate-(1+2*headway_rate)*own_a[:,1:]-hdd*own_v[:,1:]+
                                                          policy.kd*edot+policy.kp*e_meas)
            desired=np.clip(requested,-b.brake,b.acceleration_max)
            nominal=command[:,1:]+np.clip(desired-command[:,1:],-policy.comfort_jerk*dc,policy.comfort_jerk*dc)
            emergency=np.maximum(-b.brake,command[:,1:]-b.command_jerk*dc)
            next_follower=np.where(allow,nominal,emergency) if policy.shield else nominal
            target_leader=np.where((t>=leader_start)&(t<leader_start+leader_duration),leader_brake,0.)
            next_leader=command[:,0]+np.clip(target_leader-command[:,0],-b.command_jerk*dc,b.command_jerk*dc)
            next_command=np.concatenate([next_leader[:,None],next_follower],axis=1)
            jerk_energy+=dc*np.mean(((next_command[:,1:]-command[:,1:])/dc)**2,axis=1)
            command=next_command
            if profile.copies and control_tick%10 in profile.release_ticks():
                common=fade.standard_normal((r,1,4))+1j*fade.standard_normal((r,1,4))
                individual=fade.standard_normal((r,links,4))+1j*fade.standard_normal((r,links,4))
                innovation=(np.sqrt(rho)*common+np.sqrt(1-rho)*individual)/np.sqrt(2)
                innovation=np.einsum('rlk,ljk->rlj',innovation,cholesky)
                ar=environment.period_correlation;z=innovation if packet_trials==0 else ar*z+np.sqrt(1-ar*ar)*innovation
                rice=10**.3;fading_gain=np.abs(np.sqrt(rice/(rice+1))+z/np.sqrt(rice+1))**2
                d=np.maximum(position[:,:-1]-position[:,1:],.1)
                desired_dbm=29-(32.4+20*np.log10(d)+20*np.log10(5.9))-shadow
                interference=2*10**((29-(32.4+20*np.log10(300)+20*np.log10(5.9))+environment.interference_shift_db)/10)
                noise=10**((-174+10*np.log10(profile.prbs*12*30e3)+9)/10)
                sinr=(10**(desired_dbm/10)/(interference+noise))[:,:,None]*fading_gain
                success=decode.random((r,links,4))>=decode_error(sinr,grant)
                success=success[:,:,:profile.copies]
                if model.radio_mode=='perfect':success[:]=True
                if model.radio_mode=='absent':success[:]=False
                any_success=success.any(axis=2);first=np.min(np.where(success,copy_end[None,:,:],np.inf),axis=2)
                packet_lost+=np.sum(~any_success,axis=1);packet_trials+=links
                pending_tick=np.full((r,links),-1,dtype=int)
                pending_tick[any_success]=tick+np.ceil(first[any_success]/dt-1e-10).astype(int)
                pending_a=own_a[:,:-1].copy();pending_u=command[:,:-1].copy();pending_stamp=t
        effort+=dt*np.mean(command[:,1:]**2,axis=1)
        position,velocity,acceleration=plant_step(position,velocity,acceleration,command,eta,dt)
        next_headway=headway+dt*headway_rate+.5*dt*dt*hdd
        next_rate=headway_rate+dt*hdd;overshoot=next_headway<profile.h_target
        headway=np.maximum(profile.h_target,next_headway);headway_rate=np.where(overshoot,0.,np.minimum(next_rate,0.))
        bad=(peak_error>model.tracking_limit_m)|(min_clearance<b.minimum_clearance_m)
        if first_failure is None and np.any(bad):
            index=int(np.flatnonzero(bad)[0]);first_failure=dict(episode=index,time_s=t,headway=headway[index].tolist(),
                clearance_m=clearance[index].tolist(),tracking_error_m=error[index].tolist(),
                observer_lower=pred_a_lower[index].tolist(),packet_age_s=finite_age[index].tolist())
    for value in [position,velocity,acceleration,headway,peak_error,min_clearance,gain]:
        if not np.all(np.isfinite(value)):raise FloatingPointError('Nonfinite physical state/metric')
    if np.any(observer_breaches):raise RuntimeError('The acceleration lower-bound certificate was violated')
    if policy.shield and np.any(guarantee_breaches):raise RuntimeError('The braking-envelope safety certificate was violated')
    tracking=peak_error>model.tracking_limit_m;clearance_fail=min_clearance<b.minimum_clearance_m
    incomplete=~np.isfinite(completion_time)
    failed=tracking|clearance_fail|incomplete|initial_uncertified
    gain=np.maximum(0.,gain-dt*np.mean(np.clip(profile.h_initial-actual_headway,0,max(0.,profile.h_initial-profile.h_target)),axis=1))
    return dict(episodes=r,failures=int(failed.sum()),tracking_failures=int(tracking.sum()),clearance_failures=int(clearance_fail.sum()),
        completion_failures=int(incomplete.sum()),initial_uncertified=int(initial_uncertified.sum()),
        safety_certificate_breaches=int(guarantee_breaches.sum()),observer_bound_breaches=int(observer_breaches.sum()),
        episode_violation=failed.astype(int).tolist(),peak_error_m=peak_error.tolist(),minimum_clearance_m=min_clearance.tolist(),
        completion_time_s=np.where(incomplete,None,completion_time).tolist(),
        realized_gain_seconds=(gain/model.horizon_s).tolist(),successful_gain_seconds=(gain/model.horizon_s*(~failed)).tolist(),
        control_effort=effort.tolist(),jerk_energy=jerk_energy.tolist(),shield_blocks=shield_blocks.tolist(),
        packet_failures=int(packet_lost.sum()),packet_trials_per_episode=packet_trials,
        maximum_packet_age_s=max_age.tolist(),first_failure=first_failure,
        model=asdict(model),policy=asdict(policy),bounds=asdict(b),environment=asdict(environment),proof_table_id=b.key,
        limitations='Assumption-conditional braking/observer proofs; sampled tracking and completion risk. '
                    'Radio is uncalibrated and inputs are synthetic. No universal string-stability or real-road guarantee.')
