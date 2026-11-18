"""Synthetic physical-coordinate episode replay for the Guard prototype.

The 30 Hz packet release clock is rounded up to the integration grid. Arrival
times include scheduled copy completion and 1 ms processing, also rounded up;
no message is consumed early. Controller and actuator are updated separately.
The plant uses exact constant-command integration over each dt, with sampled
nonlinear saturation, jerk limits and a nonnegative-speed constraint.

This is an independent implementation from simulation/vectorized.py, but not
an independently validated backend. Fading/decoder/radar/vehicle distributions
are illustrative. It does not establish real vehicle or NR performance.
"""
from dataclasses import asdict, dataclass
import hashlib

import numpy as np

from gapslice.guard.phy import decode_error, transport
from gapslice.guard.profiles import Profile


@dataclass(frozen=True)
class Environment:
    name: str
    coherence_s: float
    coherence_prbs: float
    period_correlation: float
    cross_link_correlation: float
    shadow_sigma_db: float
    blocked: bool=False
    interference_shift_db: float=0.

    def __post_init__(self):
        if (min(self.coherence_s,self.coherence_prbs)<=0 or not 0<=self.period_correlation<1 or
                not 0<=self.cross_link_correlation<=1 or self.shadow_sigma_db<0):
            raise ValueError('Invalid channel correlation, coherence or shadowing parameters')


ENVIRONMENTS={
    'nominal': Environment('nominal',.002,8.,.3,.2,2.5),
    'correlated': Environment('correlated',.020,40.,.95,.7,4.2),
    'blocked': Environment('blocked',.020,40.,.95,.7,4.2,True,3.),
}


@dataclass(frozen=True)
class Model:
    horizon_s: float=40.
    dt_s: float=.002
    packet_period_s: float=1/30
    processing_s: float=.001
    ramp_start_s: float=2.
    maximum_tracking_error_m: float=5.
    minimum_clearance_m: float=2.
    standstill_m: float=2.
    truck_length_m: float=16.5
    initial_speed_mps: float=80/3.6
    follower_acceleration_min: float=-6.
    follower_acceleration_max: float=2.
    follower_jerk_mps3: float=2.5
    leader_jerk_mps3: float=8.
    packet_ttl_s: float=5/30
    range_noise_sd_m: float=.05
    velocity_noise_sd_mps: float=.02
    initial_velocity_error_mps: float=.15
    initial_gap_error_m: float=.25
    initial_acceleration_error_mps2: float=.05
    leader_brake_min_mps2: float=-6.
    leader_brake_max_mps2: float=-3.
    completion_tolerance_s: float=.01
    governor_error_margin_m: float=1.
    governor_closing_speed_mps: float=1.5
    governor_braking_threshold_mps2: float=-.5
    governor_speed_excess_mps: float=2.
    governor_max_age_s: float=2/30
    data_namespace: str='exploratory-guard-v1'
    radio_mode: str='surrogate'  # perfect/absent are explicit diagnostic controls


def stream(seed, split, component):
    if split not in {'design','calibration','test','verification'}:
        raise ValueError('Unknown independent-data split')
    key=f'GapSlice-Guard-v1/{seed}/{split}/{component}'.encode()
    entropy=np.frombuffer(hashlib.sha256(key).digest(),dtype=np.uint32).tolist()
    return np.random.default_rng(np.random.SeedSequence(entropy))


def gap_reference(t, profile, model):
    """Smooth endpoint-zero-derivative cubic transition, h and dh/dt."""
    fraction=np.clip((t-model.ramp_start_s)/profile.ramp_s,0.,1.)
    shape=3*fraction**2-2*fraction**3
    h=profile.h_initial+(profile.h_target-profile.h_initial)*shape
    derivative=(profile.h_target-profile.h_initial)*6*fraction*(1-fraction)/profile.ramp_s
    return float(h),float(derivative)


def repeat_cholesky(profile, environment):
    """PSD exponential time/frequency covariance for synthetic repeat gains."""
    placements=profile.placements()
    result=[]
    for link in range(profile.n_trucks-1):
        pp=[p for p in placements if p.job.packet==f'p/{link}']
        time=[p.slot*profile.slot_s for p in pp]
        freq=[p.first_prb for p in pp]
        # Always draw four Gaussian innovations: paired seeds are not changed
        # by a candidate using fewer blind copies.
        while len(time)<4:
            time.append(time[-1]+profile.slot_s)
            freq.append(freq[-1])
        tt=np.abs(np.subtract.outer(time,time))
        ff=np.abs(np.subtract.outer(freq,freq))
        covariance=np.exp(-tt/environment.coherence_s-ff/environment.coherence_prbs)
        result.append(np.linalg.cholesky(covariance+1e-12*np.eye(4)))
    return np.asarray(result)


def simulate(profile, environment, seed, episodes, split, model=None):
    profile.check()
    model=Model() if model is None else model
    if (episodes<1 or model.horizon_s <= model.ramp_start_s+profile.ramp_s or
            model.dt_s <= 0 or model.radio_mode not in {'surrogate','perfect','absent'}):
        raise ValueError('Invalid episode count, integration grid, horizon or radio mode')
    if not np.isclose(.010/model.dt_s,round(.010/model.dt_s)):
        raise ValueError('Integration step must divide the 10 ms deadline')
    if profile.deadline_slots*profile.slot_s+model.processing_s > .010+1e-12:
        raise ValueError('Configured processing plus radio exceeds the 10 ms deadline')
    n=profile.n_trucks;links=n-1;r=episodes;dt=model.dt_s
    def rng(component):return stream(seed,split,model.data_namespace+'/'+component)
    plant=rng('plant');leader=rng('leader')
    fade_rng=rng('fading');decode_rng=rng('decode')
    sensor_rng=rng('sensor');shadow_rng=rng('shadow')
    eta=plant.uniform(.25,.45,(r,n))
    velocity=np.full((r,n),model.initial_speed_mps)+plant.uniform(-model.initial_velocity_error_mps,model.initial_velocity_error_mps,(r,n))
    acceleration=plant.uniform(-model.initial_acceleration_error_mps2,model.initial_acceleration_error_mps2,(r,n));command=np.zeros((r,n))
    position=np.zeros((r,n))
    initial_gaps=model.standstill_m+profile.h_initial*velocity[:,1:]+plant.uniform(-model.initial_gap_error_m,model.initial_gap_error_m,(r,links))
    position[:,1:]=-np.cumsum(model.truck_length_m+initial_gaps,axis=1)
    brake_start=leader.uniform(3.,8.,r)
    brake_duration=leader.uniform(1.5,2.5,r)
    brake_amplitude=leader.uniform(model.leader_brake_min_mps2,model.leader_brake_max_mps2,r)
    # Shared and individual log-shadowing, fixed within each complete episode.
    rho=environment.cross_link_correlation
    shadow=environment.shadow_sigma_db*(np.sqrt(rho)*shadow_rng.standard_normal((r,1))+
                                       np.sqrt(1-rho)*shadow_rng.standard_normal((r,links)))
    if environment.blocked:
        shadow[:,links//2]+=9.+4.5*shadow_rng.standard_normal(r)
    z=np.zeros((r,links,4),dtype=complex)
    chol=repeat_cholesky(profile,environment)
    latest=np.zeros((r,links));last_timestamp=np.zeros((r,links))
    pending_value=np.zeros((r,links));pending_arrival=np.full((r,links),-1,dtype=int)
    pending_timestamp=0.
    placement=profile.placements()
    copy_end=np.zeros((links,profile.copies))
    for link in range(links):
        pp=[p for p in placement if p.job.packet==f'p/{link}']
        copy_end[link]=[(p.slot+1)*profile.slot_s+model.processing_s for p in pp]
    grant=transport(profile.prbs,profile.payload_bytes)
    # Exact ZOH coefficients for each episode/vehicle actuator time constant.
    c5=np.exp(-dt/eta);c6=1-c5;c3=eta*c6;c4=dt-c3
    c1=eta*(dt-eta*c6);c2=dt**2/2-eta*dt+eta**2*c6
    peak_error=np.zeros(r);min_clearance=np.full(r,np.inf);max_age=np.zeros(r)
    packet_failures=np.zeros(r,dtype=int);packet_total=0
    first_failure=None
    phase=np.zeros((r,links));headway=np.full((r,links),profile.h_initial)
    completion_time=np.full(r,np.inf)
    all_release=np.ceil(np.arange(0,model.horizon_s,model.packet_period_s)/dt-1e-10).astype(int)
    releases=set(all_release.tolist())
    ticks=int(np.ceil(model.horizon_s/dt))
    for tick in range(ticks+1):
        t=tick*dt
        arrived=pending_arrival==tick
        latest=np.where(arrived,pending_value,latest)
        last_timestamp=np.where(arrived,pending_timestamp,last_timestamp)
        if tick in releases:
            common=fade_rng.standard_normal((r,1,4))+1j*fade_rng.standard_normal((r,1,4))
            individual=fade_rng.standard_normal((r,links,4))+1j*fade_rng.standard_normal((r,links,4))
            innovation=(np.sqrt(rho)*common+np.sqrt(1-rho)*individual)/np.sqrt(2)
            innovation=np.einsum('rlk,ljk->rlj',innovation,chol)
            ar=environment.period_correlation
            # Correct stationary initialization: the first packet is not a
            # low-variance transient of a zero-initialized AR process.
            z=innovation if packet_total==0 else ar*z+np.sqrt(1-ar**2)*innovation
            k=10**(3/10)
            gains=np.abs(np.sqrt(k/(k+1))+z/np.sqrt(k+1))**2
            distance=np.maximum(position[:,:-1]-position[:,1:],.1)
            desired_dbm=29.-(32.4+20*np.log10(distance)+20*np.log10(5.9))-shadow
            interference=2*10**((29.-(32.4+20*np.log10(300)+20*np.log10(5.9))+
                                 environment.interference_shift_db)/10)
            noise=10**((-174+10*np.log10(profile.prbs*12*30e3)+9)/10)
            sinr=(10**(desired_dbm/10)/(interference+noise))[:,:,None]*gains
            error=decode_error(sinr,grant)
            uniform=decode_rng.random((r,links,4))
            success=uniform[:,:,:profile.copies] >= error[:,:,:profile.copies]
            if model.radio_mode=='perfect':success[:]=True
            if model.radio_mode=='absent':success[:]=False
            earliest=np.min(np.where(success,copy_end[None,:,:],np.inf),axis=2)
            any_success=success.any(axis=2)
            packet_failures+=np.sum(~any_success,axis=1)
            packet_total+=links
            pending_arrival=np.full((r,links),-1,dtype=int)
            pending_arrival[any_success]=tick+np.ceil(earliest[any_success]/dt-1e-10).astype(int)
            pending_value=command[:,:-1].copy();pending_timestamp=t
        if profile.governor:
            h=headway
        else:
            h,dh=gap_reference(t,profile,model)
        clearance=position[:,:-1]-position[:,1:]-model.truck_length_m
        error=clearance-model.standstill_m-h*velocity[:,1:]
        peak_error=np.maximum(peak_error,np.max(np.abs(error),axis=1))
        min_clearance=np.minimum(min_clearance,np.min(clearance,axis=1))
        age=t-last_timestamp
        max_age=np.maximum(max_age,np.max(age,axis=1))
        bad=(peak_error>model.maximum_tracking_error_m)|(min_clearance<model.minimum_clearance_m)
        if first_failure is None and np.any(bad):
            index=int(np.flatnonzero(bad)[0])
            first_failure=dict(episode=index,time_s=t,h=np.broadcast_to(h,(r,links))[index].tolist(),clearance_m=clearance[index].tolist(),
                tracking_error_m=error[index].tolist(),velocity_mps=velocity[index].tolist(),
                acceleration_mps2=acceleration[index].tolist(),packet_age_s=age[index].tolist())
        completed=np.all(np.abs(h-profile.h_target)<=model.completion_tolerance_s,axis=1) if profile.governor else np.full(r,abs(h-profile.h_target)<=model.completion_tolerance_s)
        completion_time=np.where(completed&~np.isfinite(completion_time),t,completion_time)
        if tick==ticks:break
        target_leader=np.where((t>=brake_start)&(t<brake_start+brake_duration),brake_amplitude,0.)
        # Same declared controller for every communication method/baseline.
        sensed_e=error+sensor_rng.normal(0,model.range_noise_sd_m,(r,links))
        relative_velocity=velocity[:,:-1]-velocity[:,1:]+sensor_rng.normal(0,model.velocity_noise_sd_mps,(r,links))
        if profile.governor:
            # Local observables only: range/relative speed, own acceleration,
            # received predecessor command, packet timestamp and own speed.
            allow=((t>=model.ramp_start_s)&(np.abs(sensed_e)<model.governor_error_margin_m)&
                   (relative_velocity>-model.governor_closing_speed_mps)&
                   (acceleration[:,1:]>model.governor_braking_threshold_mps2)&
                   (latest>model.governor_braking_threshold_mps2)&(age<=model.governor_max_age_s)&
                   (velocity[:,1:]<model.initial_speed_mps+model.governor_speed_excess_mps))
            next_phase=np.minimum(phase+allow*dt/profile.ramp_s,1.)
            next_headway=profile.h_initial+(profile.h_target-profile.h_initial)*(3*next_phase**2-2*next_phase**3)
            dh=(next_headway-headway)/dt
        derivative=relative_velocity-h*acceleration[:,1:]-dh*velocity[:,1:]
        feedforward=np.where(age<=model.packet_ttl_s,latest,0.)
        du=dt/h*(-command[:,1:]+.2*sensed_e+.7*derivative+feedforward)
        next_command=command.copy()
        next_command[:,0]+=np.clip(target_leader-command[:,0],-model.leader_jerk_mps3*dt,model.leader_jerk_mps3*dt)
        next_command[:,1:]=np.clip(command[:,1:]+np.clip(du,-model.follower_jerk_mps3*dt,model.follower_jerk_mps3*dt),
                                                   model.follower_acceleration_min,model.follower_acceleration_max)
        displacement=dt*velocity+c1*acceleration+c2*command
        position+=np.maximum(displacement,0.)
        velocity=np.maximum(velocity+c3*acceleration+c4*command,0.)
        acceleration=c5*acceleration+c6*command
        command=next_command
        if profile.governor:
            phase=next_phase;headway=next_headway
    tracking=peak_error>model.maximum_tracking_error_m
    if any(not np.all(np.isfinite(value)) for value in [peak_error,min_clearance,max_age,position,velocity,acceleration,command]):
        raise FloatingPointError('Non-finite physical state or metric; refusing a qualification record')
    clearance=min_clearance<model.minimum_clearance_m
    completion=~np.isfinite(completion_time)
    violation=tracking|clearance|completion
    if first_failure is None and np.any(completion):
        index=int(np.flatnonzero(completion)[0])
        first_failure=dict(episode=index,time_s=model.horizon_s,reason='completion deadline',
            h=np.broadcast_to(h,(r,links))[index].tolist())
    return dict(episodes=r,failures=int(violation.sum()),tracking_failures=int(tracking.sum()),
        clearance_failures=int(clearance.sum()),observed_nonpositive_clearance=int((min_clearance<=0).sum()),
        completion_failures=int(completion.sum()),
        completion_time_s=np.where(completion,None,completion_time).tolist(),
        episode_violation=violation.astype(int).tolist(),peak_error_m=peak_error.tolist(),
        minimum_clearance_m=min_clearance.tolist(),maximum_packet_age_s=max_age.tolist(),
        episode_packet_loss_fraction=(packet_failures/packet_total).tolist(),
        packet_trials_per_episode=packet_total,packet_failures=int(packet_failures.sum()),
        first_failure=first_failure,model=asdict(model),environment=asdict(environment),
        numerical_grid='plant/controller dt; packet releases and arrivals rounded up, never early',
        limitations='Synthetic finite-horizon outcomes sampled on the integration grid, surrogate decoder and illustrative uncertainty. '
                    'No string-stability, physical safety, formal privacy or NR link-level validation claim.')
