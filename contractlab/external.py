"""External SUMO validation and native published second-order CCC checks.

SUMO-native ACC/CACC/IDM retain their built-in safety behavior. Custom controls
have speedMode=0 (no hidden Krauss clamp), explicit command jerk/lag, and the
shared backup shield. The primary proof does NOT transfer to SUMO's integration.
Native CACC uses its ideal cooperative model, not our packet delivery stream.
"""
from dataclasses import asdict
from pathlib import Path
import subprocess
import time
import uuid
import numpy as np
from scipy.integrate import solve_ivp
from contractlab.baselines import ccc,ccc_time_headway_filter,adapted_nominal
from contractlab.specs import Policy
from gapslice.certified.observer import Observer
from gapslice.certified.safety import Shield


def native_ccc():
    """Native Eq.1-3 + TH filter, Table I parameters; not digitized Fig.2 data."""
    results=[]
    for B,filtered in [(.6,False),(.3,False),(.3,True)]:
        def rhs(t,x):
            d,v,vl=x;al=-3. if 2<=t<7 and vl>0 else 0.
            desired=float(ccc(d,v,vl,al,.6,A=.4,B=B,C=0.,standstill=5.,speed_limit=15.))
            u=float(ccc_time_headway_filter(desired,d,v,vl)) if filtered else desired
            return [vl-v,u,al]
        sol=solve_ivp(rhs,(0,12),[30.,15.,15.],rtol=1e-9,atol=1e-10,max_step=.005)
        if not sol.success:raise RuntimeError(sol.message)
        h=(sol.y[0]-1)/1.67-sol.y[1]
        if filtered and min(h)<-1e-5:raise RuntimeError('Native CBF invariant cross-check failed')
        results.append(dict(B=B,filtered=filtered,minimum_th_barrier=float(min(h)),minimum_gap_m=float(min(sol.y[0]))))
    return dict(results=results,scope='Native published equations and Table I gains, declared braking input; equation-level validation, not an exact figure reproduction')


def network(folder):
    import sumolib
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    nodes=folder/'nodes.xml';edges=folder/'edges.xml';net=folder/'road.net.xml'
    nodes.write_text('<nodes><node id="a" x="0" y="0"/><node id="b" x="8000" y="0"/></nodes>')
    edges.write_text('<edges><edge id="road" from="a" to="b" numLanes="1" speed="40"/></edges>')
    subprocess.run([sumolib.checkBinary('netconvert'),'--node-files',str(nodes),'--edge-files',str(edges),
                    '--output-file',str(net),'--no-warnings','true'],check=True,capture_output=True,text=True,timeout=60)
    return net


def episode(folder,backend,seed,table,n=5,target=.9,horizon=40.,dt=.01,radio='perfect',network_path=None):
    import traci
    import traci.constants as tc
    import sumolib
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    net=network_path or network(folder)
    native=backend in {'SUMO_IDM','SUMO_ACC','SUMO_CACC'}
    mode=backend.removeprefix('SUMO_') if native else 'Krauss'
    random=np.random.default_rng(seed);speed=float(random.uniform(16.7,30.));brake=float(random.uniform(3.,6.))
    routes=folder/'routes.xml'
    vehicles=''.join(f'<vehicle id="v{i}" type="truck" route="r" depart="0" departPos="{1500-i*(16.5+2+1.5*speed)}" departSpeed="{speed}"/>' for i in range(n))
    routes.write_text(f'<routes><vType id="truck" length="16.5" minGap="2" accel="2" decel="6" emergencyDecel="6" tau="{target}" sigma="0" maxSpeed="35" carFollowModel="{mode}"/><route id="r" edges="road"/>{vehicles}</routes>')
    label='contract-'+uuid.uuid4().hex;log=folder/'sumo.log'
    args=[sumolib.checkBinary('sumo'),'-n',str(net),'-r',str(routes),'--step-length',str(dt),
          '--step-method.ballistic','true','--seed',str(seed),'--no-step-log','true',
          '--duration-log.disable','true','--collision.action','warn','--collision.mingap-factor','0',
          '--time-to-teleport','-1','--log',str(log)]
    start=time.perf_counter();connection=None
    try:
        traci.start(args,label=label,doSwitch=False,stdout=subprocess.DEVNULL,numRetries=5)
        connection=traci.getConnection(label);connection.simulationStep()
        ids=[f'v{i}' for i in range(n)]
        if set(connection.vehicle.getIDList())!=set(ids):raise RuntimeError('SUMO could not insert complete platoon')
        for vid in ids:connection.vehicle.setLaneChangeMode(vid,0);connection.vehicle.subscribe(vid,[tc.VAR_LANEPOSITION,tc.VAR_SPEED,tc.VAR_ACCELERATION])
        for vid in (ids[:1] if native else ids):connection.vehicle.setSpeedMode(vid,0)
        min_gap=float('inf');peak=0.;gain=0.;dwell=0.;attained=False;collisions=0;interventions=0
        commanded=np.zeros(n);lag_a=np.zeros(n);headway=np.full((1,n-1),1.5);rate=np.zeros_like(headway)
        pa=np.zeros((1,n-1));stamp=-float('inf');eta=random.uniform(.25,.45,n)
        policy=Policy(controller='hold' if native else backend)
        with Shield(table,verify_hashes=False) as shield:
            observer=Observer((1,n-1),shield.bounds);b=shield.bounds
            # Nominal observer and control updates share the primary 10ms clock.
            # SUMO's independent ballistic integration differs from the primary
            # exact-lag 2ms plant; no lower-bound certificate is transferred.
            for step in range(round(horizon/dt)):
                t=step*dt;rows=[connection.vehicle.getSubscriptionResults(v) for v in ids]
                if any(x is None for x in rows):raise RuntimeError('A SUMO vehicle disappeared')
                x=np.array([r[tc.VAR_LANEPOSITION] for r in rows]);v=np.array([r[tc.VAR_SPEED] for r in rows])
                a=np.array([r[tc.VAR_ACCELERATION] for r in rows]);d=x[:-1]-x[1:]-16.5;dv=v[:-1]-v[1:]
                min_gap=min(min_gap,float(min(d)));peak=max(peak,float(max(abs(d-2-headway[0]*v[1:]))))
                at=bool(np.all(abs(d-2-target*v[1:])<=1.));dwell=dwell+dt if at else 0.;attained|=dwell>=2
                gain+=dt*float(np.mean(np.clip(1.5-(d-2)/np.maximum(v[1:],2),0,1.5-target)))
                collisions+=connection.simulation.getCollidingVehiclesNumber()
                lead=-brake if 4<=t<6.5 else 0.
                commanded[0]+=np.clip(lead-commanded[0],-8*dt,8*dt)
                if not native:
                    if step%10 in {0,4,7} and (radio=='perfect' or random.random()>.7):pa=a[:-1][None,:].copy();stamp=t
                    age=np.full_like(pa,t-stamp)
                    observer.update(v[:-1][None,:])
                    estimate=observer.feedforward(pa,age,backend if backend in {'hold','radar','fused'} else 'hold')
                    lower=np.full_like(pa,-6.)  # Conservative; no unvalidated SUMO observer certificate.
                    allow,_=shield.decide(d[None,:]-.1,v[None,1:]+.01,np.clip(a[None,1:]+.02,-6,2),
                        commanded[None,1:],np.maximum(0,v[None,:-1]-.05),lower,True)
                    error=d[None,:]-2-headway*v[None,1:]
                    healthy=(t>=2)&(abs(error)<1)&(dv[None,:]>-1.5)&(a[None,1:]>-.75)&(estimate>-.75)&allow
                    desired_rate=-np.minimum(.15,np.sqrt(.16*np.maximum(0,headway-target)))*healthy
                    hdd=np.clip((desired_rate-rate)/.25,-.08,.08)
                    edot=dv[None,:]-headway*a[None,1:]-rate*v[None,1:]
                    requested=a[None,1:]+.35/headway*(estimate-(1+2*rate)*a[None,1:]-hdd*v[None,1:]+1.8*edot+.8*error)
                    if backend in {'idm','ccc','ccc_cbf'}:requested=adapted_nominal(policy,d[None,:],v[None,1:],v[None,:-1],a[None,1:],estimate,lower,headway,speed+2,2,.35,rate,hdd)
                    nominal=commanded[1:]+np.clip(np.clip(requested[0],-6,2)-commanded[1:],-2.5*dt,2.5*dt)
                    commanded[1:]=np.where(allow[0],nominal,np.maximum(-6,commanded[1:]-8*dt));interventions+=int((~allow).sum())
                    hn=headway+dt*rate+.5*dt*dt*hdd;rate=np.where(hn<target,0,np.minimum(0,rate+dt*hdd));headway=np.maximum(target,hn)
                lag_a=commanded+(lag_a-commanded)*np.exp(-dt/eta)
                for i in (range(1) if native else range(n)):
                    connection.vehicle.setSpeed(ids[i],float(max(0,v[i]+lag_a[i]*dt)))
                connection.simulationStep()
        return dict(backend=backend,seed=seed,n=n,target=target,minimum_clearance_m=min_gap,
            clearance_violation=min_gap<2,peak_moving_reference_error_m=peak,physical_target_attained=bool(attained),
            realized_gain_s=gain/horizon,collision_events=collisions,shield_interventions=interventions,
            wall_s=time.perf_counter()-start,radio=radio if not native else 'native-model ideal cooperation',
            guarantee='No transferred analytic certificate; independent SUMO cross-model test',
            scope='Native SUMO models retain default safety overrides; custom modes disable hidden speed checks. These implementation differences are reported, not concealed.')
    finally:
        if connection is not None:connection.close()
