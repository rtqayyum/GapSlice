"""Predeclared fresh splits and finite design/qualification menus."""
from dataclasses import asdict,replace
from itertools import product
from contractlab.common import sha
from contractlab.specs import Policy,Model,CONTEXTS,CONTROLLERS
from gapslice.certified.profiles import Profile


def configuration(preset):
    settings={
        'smoke':dict(design_n=2,calibration_n=4,test_n=4,diagnostic_n=2,batch=2,phy_frames=1,external_seeds=1,external_horizon=4.,allocation_repeats=1),
        'pilot':dict(design_n=32,calibration_n=256,test_n=256,diagnostic_n=128,batch=64,phy_frames=8,external_seeds=2,external_horizon=40.,allocation_repeats=2),
        'research':dict(design_n=64,calibration_n=65536,test_n=65536,diagnostic_n=2048,batch=128,phy_frames=256,external_seeds=32,external_horizon=40.,allocation_repeats=30),
    }
    if preset not in settings:raise ValueError('Unknown preset')
    return dict(schema=1,preset=preset,namespace='contract-framework-fresh-v1-'+preset,
                horizon_s=12. if preset=='smoke' else 40.,contexts=['nominal'] if preset=='smoke' else list(CONTEXTS),
                risk_family_alpha=.025,benefit_family_alpha=.025,probability_scale=1000000,
                deployment_risk_budgets=[.01,.02,.05],loads=[8,16,32,64,128],
                physical_target_tolerance_m=1.,physical_target_dwell_s=2.,
                **settings[preset])


def cases(config):
    if config['preset']=='smoke':grid=[(3,1.2,51)]
    elif config['preset']=='pilot':grid=[(3,1.2,51),(5,.9,106)]
    else:grid=list(product([3,5],[.9,1.2],[51,106]))
    result=[dict(n=n,target=h,cap=cap,payload=300,id=sha([n,h,cap,300])[:16]) for n,h,cap in grid]
    if config['preset']!='smoke':
        for n,h,cap in ([(5,.9,106)] if config['preset']=='pilot' else [(3,.9,51),(5,1.2,106)]):
            result.append(dict(n=n,target=h,cap=cap,payload=600,id=sha([n,h,cap,600])[:16]))
    return result


def profiles(case,smoke=False):
    base=Profile(n_trucks=case['n'],h_target=case['target'],cap=case['cap'],payload_bytes=case['payload'])
    result=[replace(base,prbs=0,copies=0,pattern='none',layout='none',phase=0)]
    grid=product([20] if smoke else [10,20,40],[1] if smoke else [1,2],['serial'] if smoke else ['serial','parallel'],[0] if smoke else [0,3])
    seen=set()
    for prbs,copies,layout,phase in grid:
        p=replace(base,prbs=prbs,copies=copies,pattern='hopped',layout=layout,phase=phase)
        try:p.check()
        except ValueError:continue
        geometry=(tuple(p.relative()),phase)
        if geometry not in seen:seen.add(geometry);result.append(p)
    return result


def cell(case,profile,policy,context,config,kind='main'):
    model=Model(horizon_s=config['horizon_s'],data_namespace=config['namespace'],rician_k_db=CONTEXTS[context]['k_db'])
    if kind=='perfect_radio':model=replace(model,radio_mode='perfect')
    if kind=='slow_hard_shift':model=replace(model,eta_mode='slow',brake_mode='hard')
    if kind=='alternating_hard_shift':model=replace(model,eta_mode='alternating',brake_mode='hard')
    if kind=='no_shield':policy=replace(policy,shield=False)
    value=dict(case=case,profile=asdict(profile),policy=asdict(policy),context=context,model=asdict(model),kind=kind)
    return dict(id=sha(value)[:24],**value)


def design_cells(config):
    result={}
    for case in cases(config):
        for p in profiles(case,config['preset']=='smoke'):
            for controller in CONTROLLERS:
                # Locally sensed modes never buy radio that they do not consume.
                if controller in {'radar','idm'} and p.copies:continue
                for tune in ([0] if config['preset']=='smoke' else [0,1]):
                    policy=Policy(controller=controller,kp=.8 if tune==0 else 1.2,kd=1.8 if tune==0 else 2.2,
                                  idm_a=1.4 if tune==0 else 2.,ccc_A=.4 if tune==0 else .6,
                                  ccc_B=.6 if tune==0 else .9,ccc_C=.5)
                    c=cell(case,p,policy,'nominal',config);result[c['id']]=c
    return result


def replay_manifest(stage,cells,config):
    n=config[stage+'_n'] if stage in {'design','calibration','test'} else config['diagnostic_n']
    tasks=[]
    for cid,c in sorted(cells.items()):
        for offset in range(0,n,config['batch']):
            # Matching plant/sensor streams across policy/profile comparisons;
            # exact pairing requires the same n, context, split and batch shape.
            seed=int(sha([config['namespace'],stage,c['case']['id'],c['context'],offset])[:12],16)
            row=dict(cell=cid,offset=offset,episodes=min(config['batch'],n-offset),seed=seed)
            row['id']=sha([stage,c,row])[:24];tasks.append(row)
    return dict(stage=stage,cells=cells,tasks=tasks,config=config)
