"""Resumable contract experiment with immutable scientific manifests.

Run the module through BatchContracts on Slurm; --local is for small verification
presets only. No measured data are generated or implied by this pipeline.
"""
import argparse
from collections import defaultdict
from dataclasses import asdict,replace
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import time
import traceback
import uuid
import numpy as np

from contractlab.common import ROOT,BASE,atomic,immutable,optional,sha,digest,fingerprint,utc,snapshot_sources
from contractlab.protocol import configuration,cases,profiles,cell,design_cells,replay_manifest
from contractlab.specs import Policy,Model,CONTEXTS,CONTROLLERS
from contractlab.ldpc import Lookup
from contractlab.risk import qualify,SCALE
from gapslice.certified.profiles import Profile
from gapslice.certified.safety import Bounds,Shield,ensure_tables
from gapslice.guard.simulator import ENVIRONMENTS


def read(path):return json.loads(Path(path).read_text())
def result_path(stage,task):return Path(stage)/'results'/f"{task['id']}.json"


def load(stage,task):
    p=result_path(stage,task)
    if not p.exists():return None
    record=read(p)
    if record['task_sha256']!=sha(task):raise RuntimeError(f'Changed task: {p}')
    if record.get('raw') and digest(p.parent/record['raw'])!=record['raw_sha256']:
        raise RuntimeError(f'Corrupt raw results: {p}')
    return record


def manifest(study,name,cells=None,tasks=None):
    config=read(study/'protocol.json')['config']
    value=replay_manifest(name,cells,config) if cells is not None else dict(stage=name,tasks=tasks,config=config)
    value['source_sha256']=read(study/'protocol.json')['source_sha256']
    if cells is not None:
        inputs=[study/'tables.json',study/'phy_lookup.json']
        inputs.extend(Path(p)/'certificate.json' for p in set(read(study/'tables.json').values()))
        value['input_hashes']={str(p.relative_to(study)):digest(p) for p in inputs}
    return immutable(study/name/'manifest.json',value)


def raw_vectors(result):
    arrays={}
    for key,value in result.items():
        if isinstance(value,list) and len(value)==result['episodes']:
            arrays[key]=np.asarray(value,dtype=float)
    return arrays


def execute(study,m,task,rank):
    kind=m['stage'];config=m['config'];work=study/'work'/kind/task['id']
    if kind.startswith('phy_'):
        from contractlab.ldpc import point
        return dict(result=point(task))
    if kind=='external':
        from contractlab.external import episode
        table=read(study/'tables.json')['nominal']
        result=episode(work,task['backend'],task['seed'],table,n=task['n'],target=task['target'],
                       horizon=task['horizon'],radio=task['radio'],network_path=study/'sumo'/'road.net.xml')
        return dict(result=result)
    if kind=='packet':
        from contractlab.schedulers import benchmark
        return dict(result=benchmark(task['seed'],task['links'],task['cap'],task['method']))
    if kind=='allocation':
        from contractlab.evaluation import allocation_trial
        return dict(result=allocation_trial(study,task))
    c=m['cells'][task['cell']];p=Profile(**c['profile']);policy=Policy(**c['policy']);model=Model(**c['model'])
    split=kind if kind in {'design','calibration','test'} else 'verification'
    from contractlab.simulator import simulate
    curve=Lookup(read(study/'phy_lookup.json')['rows'])
    table=read(study/'tables.json')[c['context']]
    result=simulate(p,policy,ENVIRONMENTS[CONTEXTS[c['context']]['radio']],task['seed'],task['episodes'],split,table,model,decoder=curve)
    vectors=raw_vectors(result)
    summary={k:v for k,v in result.items() if k not in vectors}
    summary['successful_reward_sum']=float(sum(result['successful_gain_seconds']))
    summary['realized_reward_sum']=float(sum(result['realized_gain_seconds']))
    summary['guard_s_per_episode']=result['guard_wall_s']/task['episodes']
    summary['maximum_acceleration_l2_link_gain']=float(np.max(vectors['acceleration_l2_link_gain']))
    return dict(result=summary,vectors=vectors)


def worker(path,rank,size):
    path=Path(path).resolve();stage=path.parent;study=stage.parent;m=read(path)
    protocol=read(study/'protocol.json')
    if fingerprint()!=protocol['source']:raise RuntimeError('Source/dependency fingerprint changed; never mix studies')
    for name,expected in m.get('input_hashes',{}).items():
        if digest(study/name)!=expected:raise RuntimeError('Changed frozen scientific input: '+name)
    attempt=os.environ.get('SLURM_JOB_ID','local');logs=ROOT/'logs/contracts'/study.name/attempt/m['stage']
    logs.mkdir(parents=True,exist_ok=True);progress=logs/f'progress-{rank:04d}.log'
    start=time.perf_counter();done=0;reused=0;assigned=len(m['tasks'][rank::size])
    with progress.open('a',buffering=1) as stream:
        for task in m['tasks'][rank::size]:
            prior=load(stage,task)
            if prior is not None:reused+=1;status='RESUME'
            else:
                before=time.perf_counter();cpu=time.process_time()
                try:
                    value=execute(study,m,task,rank);vectors=value.pop('vectors',None)
                    if vectors is not None:
                        folder=stage/'results';folder.mkdir(parents=True,exist_ok=True)
                        final=folder/f"{task['id']}.npz";temporary=folder/f'.partial-{uuid.uuid4().hex}'
                        with temporary.open('xb') as out:
                            np.savez_compressed(out,**vectors);out.flush();os.fsync(out.fileno())
                        os.replace(temporary,final)
                        value.update(raw=final.name,raw_sha256=digest(final))
                    value.update(task_sha256=sha(task),task=task,host=socket.gethostname(),rank=rank,attempt=attempt,
                        wall_s=time.perf_counter()-before,cpu_s=time.process_time()-cpu,
                        maximum_process_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024),utc=utc())
                    atomic(result_path(stage,task),value);done+=1;status='COMPLETE'
                except BaseException:
                    stream.write(f"FAILED task={task['id']}\n");traceback.print_exc();raise
            stream.write(f"{status} task={task['id']} cell={task.get('cell','-')}\n")
            optional(stage/'workers'/attempt/f'{rank:04d}.json',dict(rank=rank,size=size,assigned=assigned,
                fresh=done,reused=reused,processed=done+reused,wall_s=time.perf_counter()-start,utc=utc()))
    optional(stage/'workers'/attempt/f'{rank:04d}.json',dict(rank=rank,size=size,assigned=assigned,fresh=done,
        reused=reused,processed=done+reused,wall_s=time.perf_counter()-start,finished=True,utc=utc()))


def run_stage(study,path,workers,local=False):
    m=read(path);stage=path.parent
    if fingerprint()!=read(study/'protocol.json')['source']:raise RuntimeError('Source/dependencies changed during study')
    print(f"STAGE {m['stage']} tasks={len(m['tasks'])} workers={workers}",flush=True)
    if local:
        worker(path,0,1)
    else:
        attempt=os.environ['SLURM_JOB_ID'];logs=ROOT/'logs/contracts'/study.name/attempt/m['stage']
        logs.mkdir(parents=True,exist_ok=True)
        command=['srun','--ntasks='+str(workers),'--cpus-per-task=1','--wait=0','--kill-on-bad-exit=1',
                 '--distribution=block:block','--output='+str(logs/'rank-%t.out'),'--error='+str(logs/'rank-%t.err'),
                 sys.executable,'-m','contractlab.campaign','worker','--manifest',str(path)]
        subprocess.run(command,cwd=ROOT,check=True)
    # Required data commit verification. A failed worker never triggers a long
    # partial-data scan; the subprocess above raises before reaching this point.
    index=[]
    for i,t in enumerate(m['tasks']):
        record=load(stage,t)
        if record is None:raise RuntimeError('Missing required task '+t['id'])
        index.append(dict(id=t['id'],commit_sha256=digest(result_path(stage,t)),raw_sha256=record.get('raw_sha256')))
        if (i+1)%5000==0:print(f"VERIFY {m['stage']} {i+1}/{len(m['tasks'])}",flush=True)
    atomic(stage/'index.json',dict(manifest_sha256=digest(path),records=index,verified_utc=utc()))
    aggregate={}
    if 'cells' in m:
        for t in m['tasks']:
            record=load(stage,t)['result'];cid=t['cell']
            if cid not in aggregate:aggregate[cid]=dict(episodes=0,failures=0,reward_sum=0.,realized_reward_sum=0.,clearance_failures=0,
                tracking_failures=0,completion_failures=0,cpu_s=0.,guard_s=0.,maximum_batched_guard_wall_s=0.,maximum_acceleration_l2_link_gain=0.)
            row=aggregate[cid];row['episodes']+=record['episodes'];row['failures']+=record['failures']
            row['reward_sum']+=record['successful_reward_sum'];row['realized_reward_sum']+=record['realized_reward_sum']
            for name in ['clearance_failures','tracking_failures','completion_failures']:row[name]+=record[name]
            row['guard_s']+=record['guard_wall_s'];row['maximum_batched_guard_wall_s']=max(row['maximum_batched_guard_wall_s'],record['maximum_batched_guard_wall_s'])
            row['maximum_acceleration_l2_link_gain']=max(row['maximum_acceleration_l2_link_gain'],record['maximum_acceleration_l2_link_gain'])
            row['cpu_s']+=load(stage,t)['cpu_s']
    atomic(stage/'aggregate.json',aggregate)
    atomic(stage/'complete.json',dict(complete=len(index),expected=len(m['tasks']),utc=utc(),index_sha256=digest(stage/'index.json')))
    print(f"COMPLETE {m['stage']} {len(index)}/{len(m['tasks'])}",flush=True)
    return aggregate


def phy_tasks(config,split):
    tasks=[]
    from itertools import product
    for prbs,payload in product([20] if config['preset']=='smoke' else [10,20,40],
                                [300] if config['preset']=='smoke' else [300,600]):
        for snr in ([-4.,12.] if config['preset']=='smoke' else [-8.,-4.,0.,2.,4.,6.,8.,12.,16.]):
            # Independent data bits and noise for fit versus held-out code blocks.
            row=dict(prbs=prbs,payload=payload,snr_db=snr,frames=config['phy_frames'],
                     seed=int(sha([config['namespace'],split,prbs,payload,snr])[:12],16))
            row['id']=sha(row)[:24];tasks.append(row)
    return tasks


def select_design(study,cells,aggregate,config):
    selected={};groups=defaultdict(list)
    for cid,c in cells.items():groups[(c['case']['id'],c['policy']['controller'],bool(c['profile']['copies']))].append(cid)
    for group,cids in sorted(groups.items()):
        def score(cid):
            r=aggregate[cid];p=Profile(**cells[cid]['profile'])
            return (r['failures']/r['episodes'],-r['reward_sum']/r['episodes'],p.cost,cid)
        best=cells[min(cids,key=score)]
        for context in config['contexts']:
            cc=cell(best['case'],Profile(**best['profile']),Policy(**best['policy']),context,config)
            selected[cc['id']]=cc
    immutable(study/'selected.json',dict(selection='One design-selected no-radio and one radio candidate per controller/case; all policies frozen before qualification',cells=selected))
    return selected


def compile_contracts(study,cells,aggregate,protocol):
    result={};family=len(cells)
    for cid,c in sorted(cells.items()):
        r=aggregate[cid];p=Profile(**c['profile'])
        q=qualify(r['failures'],r['episodes'],r['reward_sum'],p.h_initial-p.h_target,family)
        result[cid]=dict(**c,**q,qualified=q['risk_upper']<=.05 and q['benefit_microseconds']>0,
            horizon_s=c['model']['horizon_s'],source_sha256=protocol['source_sha256'],
            qualification_distribution='Declared synthetic mixture and coded-AWGN lookup; fresh independent episodes',
            assumptions=CONTEXTS[c['context']],schedule_witness=p.check(),
            proof_table=read(study/'tables.json')[c['context']],
            event='Any >5m moving-reference tracking error, <2m sampled clearance, invalid initial backup, or no sustained physical target attainment')
    immutable(study/'contracts.json',result)
    return result


def diagnostics(cells,config):
    result={}
    # Matched policy/profile cases: radio perfect, common shield removed and
    # two explicitly out-of-mixture extreme combinations. Never re-qualify on them.
    for c in cells.values():
        if c['context']!='nominal':continue
        for kind in ['perfect_radio','no_shield','slow_hard_shift','alternating_hard_shift']:
            if kind=='perfect_radio' and not c['profile']['copies']:continue
            cc=cell(c['case'],Profile(**c['profile']),Policy(**c['policy']),'nominal',config,kind)
            result[cc['id']]=cc
    return result


def external_tasks(config):
    tasks=[]
    modes=['SUMO_IDM','SUMO_ACC','SUMO_CACC',*CONTROLLERS]
    ccase=cases(config) if config['preset']=='smoke' else [dict(n=n,target=h) for n,h in [(3,.9),(5,.9),(3,1.2),(5,1.2)]]
    for case in ccase:
        for seed in range(config['external_seeds']):
            for mode in modes:
                for radio in (['perfect','bursty'] if mode not in {'SUMO_IDM','SUMO_ACC','SUMO_CACC','radar','idm'} and config['preset']=='research' else ['perfect']):
                    row=dict(backend=mode,n=case['n'],target=case['target'],seed=seed+88801,
                             horizon=config['external_horizon'],radio=radio)
                    row['id']=sha(row)[:24];tasks.append(row)
    return tasks


def run(preset,workers,local=False):
    if local and preset!='smoke':raise RuntimeError('Local mode only allows the small verification preset')
    config=configuration(preset);source=fingerprint()
    # A changed implementation must not silently replay already-inspected test
    # streams. Pure documentation/test changes do not alter these RNG streams.
    revision=sha({k:v for k,v in source['files'].items() if k.startswith(('contractlab/','gapslice/')) or k=='requirements-contract.txt'})
    config['namespace']+='-'+revision[:16]
    protocol=dict(config=config,source=source,source_sha256=sha(source))
    study=BASE/'studies'/('contract-'+preset+'-'+sha(protocol)[:16]);study.mkdir(parents=True,exist_ok=True)
    immutable(study/'protocol.json',protocol)
    snapshot_sources(study,source)
    job=os.environ.get('SLURM_JOB_ID','local');atomic(BASE/'jobs'/f'{job}.json',dict(study=str(study),preset=preset,workers=workers))
    print(f'STUDY {study}',flush=True)
    try:
        tables={}
        for context in config['contexts']:
            errors={k:v for k,v in CONTEXTS[context].items() if k not in {'radio','k_db'}}
            tables[context]=str(ensure_tables(study/'tables',Bounds(**errors)).resolve())
            with Shield(tables[context],verify_hashes=True):pass
        immutable(study/'tables.json',tables)
        from contractlab.external import native_ccc,network
        from contractlab.ldpc import frame
        native=native_ccc()
        for b in ([20] if preset=='smoke' else [10,20,40]):
            for payload in ([300] if preset=='smoke' else [300,600]):
                if frame(b,payload,20.,8351,noise=False)['failed']:raise RuntimeError('NR LDPC noiseless roundtrip failed')
        network(study/'sumo')
        immutable(study/'native_checks.json',native)
        for phase in ['phy_fit','phy_holdout']:
            path=manifest(study,phase,tasks=phy_tasks(config,phase));run_stage(study,path,workers,local)
        fit=read(study/'phy_fit/manifest.json')
        immutable(study/'phy_lookup.json',dict(rows=[load(study/'phy_fit',t)['result'] for t in fit['tasks']],
            scope='Frozen conservative step lookup of coded AWGN Monte Carlo bounds; unmeasured fading/interference remain assumptions'))
        # All external tools are exercised BEFORE expensive qualification.
        ext=external_tasks(config)
        path=manifest(study,'external',tasks=ext);run_stage(study,path,workers,local)
        cells=design_cells(config);path=manifest(study,'design',cells=cells)
        aggregate=run_stage(study,path,workers,local);selected=select_design(study,cells,aggregate,config)
        path=manifest(study,'calibration',cells=selected);cal=run_stage(study,path,workers,local)
        contracts=compile_contracts(study,selected,cal,protocol)
        path=manifest(study,'test',cells=selected);run_stage(study,path,workers,local)
        path=manifest(study,'diagnostics',cells=diagnostics(selected,config));run_stage(study,path,workers,local)
        tasks=[]
        for links in ([8] if preset=='smoke' else [8,32,64,128]):
            for cap in ([51] if preset=='smoke' else [51,106]):
                for seed in range(2 if preset=='smoke' else 30):
                    for method in ['maxci','pf','drr']:
                        row=dict(seed=seed+7091,links=links,cap=cap,method=method);row['id']=sha(row)[:24];tasks.append(row)
        path=manifest(study,'packet',tasks=tasks);run_stage(study,path,workers,local)
        from contractlab.evaluation import allocation_tasks,report,bundle
        path=manifest(study,'allocation',tasks=allocation_tasks(config));run_stage(study,path,workers,local)
        report(study);bundle(study)
        atomic(study/'status.json',dict(state='COMPLETED',utc=utc(),job=job))
        print(f'REPORT {study}/report.html\nBUNDLE {study}/analysis_bundle.tar.gz\nEVIDENCE {study}/evidence_bundle.tar.gz',flush=True)
    except BaseException as error:
        atomic(study/'status.json',dict(state='FAILED',error=repr(error),utc=utc(),job=job,partial_results_preserved=True))
        raise
    return study


def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('run');p.add_argument('--preset',choices=['smoke','pilot','research'],required=True);p.add_argument('--workers',type=int,default=1);p.add_argument('--local',action='store_true')
    p=sub.add_parser('worker');p.add_argument('--manifest',required=True)
    args=parser.parse_args()
    if args.command=='run':run(args.preset,args.workers,args.local)
    else:worker(args.manifest,int(os.environ.get('SLURM_PROCID','0')),int(os.environ.get('SLURM_NTASKS','1')))

if __name__=='__main__':main()
