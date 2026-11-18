"""Resumable CPU campaigns for a new, explicitly exploratory method prototype.

python -m gapslice.guard.campaign local --preset smoke --workers 2
python -m gapslice.guard.campaign build --preset pilot
python -m gapslice.guard.campaign worker --manifest ABSOLUTE_PATH
python -m gapslice.guard.campaign report --manifest ABSOLUTE_PATH
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import heapq
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time
import traceback

# This import sets single-threaded BLAS before scientific modules are loaded.
from gapslice.revision.campaign import atomic_json, canonical, fingerprint, sha

ROOT=Path(__file__).resolve().parents[2]
STAGE='research_prototype_synthetic'


def source_fingerprint():
    f=fingerprint(ROOT)
    paths=[ROOT/'Batch',*sorted((ROOT/'hpc').glob('*.sh')),*sorted((ROOT/'tests').glob('test_guard*.py'))]
    f['execution_files']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return f


def configurations(preset):
    from gapslice.guard.profiles import catalog
    from gapslice.guard.simulator import Model
    if preset not in {'smoke','pilot'}:
        raise ValueError('Only smoke and exploratory pilot are authorized by this protocol')
    main=[]
    for h in ([1.] if preset=='smoke' else [.6,1.,1.5]):
        pp=catalog(h_target=h)
        if preset=='smoke':
            pp=[min(pp,key=lambda p:(p.cost,p.key)),
                next(p for p in pp if p.prbs==20 and p.copies==4 and p.pattern=='hopped')]
        main.extend(pp)
    environments=['nominal'] if preset=='smoke' else ['nominal','correlated','blocked']
    seeds=[19001] if preset=='smoke' else list(range(19001,19005))
    counts=dict(design=8,calibration=8,test=8) if preset=='smoke' else dict(design=32,calibration=512,test=512)
    model=Model(data_namespace=f'exploratory-guard-{preset}-v1')
    records=[]
    def add(kind,p,env,split,seed,episodes,physical_model=model):
        records.append(dict(kind=kind,profile_id=p.key,profile=asdict(p),environment=env,
            split=split,seed=seed,episodes=episodes,model=asdict(physical_model)))
    for p in main:
        for env in environments:
            for seed in seeds:
                for split,n in counts.items():
                    add('main',p,env,split,seed,n)
                add('no_governor',replace(p,governor=False),env,'test',seed,counts['test'])
    for p in main:
        if p.prbs==20 and p.copies==4 and p.pattern=='hopped':
            for seed in seeds:
                for governor in [True,False]:
                    add('perfect_radio',replace(p,governor=governor),'nominal','test',seed,
                        8 if preset=='smoke' else 64,replace(model,radio_mode='perfect'))
    return records


def build(preset):
    configs=configurations(preset)
    protocol=dict(episode_risk=.01,fleet_risk=.01,profile_risk_levels=[.0025,.005,.01],family_error=.05,
        domains={'los':['nominal','correlated'],'blocked':['blocked']} if preset=='pilot' else {'nominal':['nominal']},
        main_procedure='fixed_sequence',
        baselines=['bonferroni','empirical_outcome','delivery_proxy','max_reservation'],
        outcome='Any tracking error >5 m, clearance <2 m, or incomplete target-gap maneuver by 40 s',
        scope='Exploratory prototype, not final held-out evaluation or external validation')
    header=dict(schema=1,stage=STAGE,preset=preset,configs=configs,protocol=protocol,fingerprint=source_fingerprint())
    campaign=f'guard-{preset}-{sha(header)[:16]}'
    tasks=[dict(id=sha(c)[:20],config=c) for c in configs]
    if len({t['id'] for t in tasks})!=len(tasks):raise AssertionError('Duplicate tasks')
    m=dict(**header,campaign_id=campaign,tasks=tasks)
    path=ROOT/'outputs/guard/manifests'/f'{campaign}.json'
    if path.exists():
        if json.loads(path.read_text())!=m:raise RuntimeError('Refusing to overwrite a different manifest')
    else:atomic_json(path,m)
    return path


def read_manifest(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):raise ValueError('Manifest must be inside this checkout')
    m=json.loads(path.read_text())
    header={k:m[k] for k in ['schema','stage','preset','configs','protocol','fingerprint']}
    if m['stage']!=STAGE or m['campaign_id']!=f'guard-{m["preset"]}-{sha(header)[:16]}':
        raise ValueError('Manifest identity/stage mismatch')
    if m['configs']!=[t['config'] for t in m['tasks']] or any(t['id']!=sha(t['config'])[:20] for t in m['tasks']):
        raise ValueError('Task configuration/identity mismatch')
    if len({t['id'] for t in m['tasks']})!=len(m['tasks']):raise ValueError('Duplicate tasks')
    if m['fingerprint']!=source_fingerprint():
        raise RuntimeError('Source, execution scripts or environment changed; build a new campaign')
    return m


def attempt():
    value=os.environ.get('GS_OJCS_ATTEMPT',os.environ.get('SLURM_JOB_ID','local'))
    if not value or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in value):
        raise ValueError('Unsafe attempt identifier')
    return value


def shards(tasks, workers):
    """Deterministic cost-aware static assignment, not an MPI control solve."""
    if workers<1:raise ValueError('Positive worker count required')
    bins=[[] for _ in range(workers)];heap=[(0.,i) for i in range(workers)]
    def weight(t):
        c=t['config'];return (64+c['episodes'])*c['profile']['n_trucks']*c['model']['horizon_s']/c['model']['dt_s']
    for task in sorted(tasks,key=lambda t:(-weight(t),t['id'])):
        cost,rank=heapq.heappop(heap);bins[rank].append(task)
        heapq.heappush(heap,(cost+weight(task),rank))
    return bins


def worker(path,rank,world):
    from gapslice.guard.profiles import Profile
    from gapslice.guard.simulator import ENVIRONMENTS,Model,simulate
    m=read_manifest(path);base=ROOT/'outputs/guard'/m['campaign_id']
    logdir=ROOT/'logs'/m['campaign_id']/attempt();logdir.mkdir(parents=True,exist_ok=True)
    results=base/'results';results.mkdir(parents=True,exist_ok=True)
    assigned=shards(m['tasks'],world)[rank];completed=skipped=failed=0
    with (logdir/f'progress-{rank:03d}.log').open('a',buffering=1) as log:
        for i,task in enumerate(assigned,1):
            out=results/f'{task["id"]}.json'
            if out.exists():
                previous=json.loads(out.read_text())
                if previous.get('campaign_id')!=m['campaign_id'] or previous.get('id')!=task['id'] or previous.get('config')!=task['config'] or previous.get('status')!='complete':
                    raise RuntimeError('Existing task result identity/status mismatch')
                skipped+=1;continue
            start=time.perf_counter();cpu=time.process_time()
            try:
                c=task['config']
                result=simulate(Profile(**c['profile']),ENVIRONMENTS[c['environment']],c['seed'],c['episodes'],c['split'],Model(**c['model']))
                peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024)
                atomic_json(out,dict(id=task['id'],campaign_id=m['campaign_id'],stage=STAGE,status='complete',
                    config=c,metrics=result,rank=rank,attempt=attempt(),wall_s=time.perf_counter()-start,
                    cpu_s=time.process_time()-cpu,process_peak_rss_mib=peak,hostname=platform.node()))
                failure=results/f'{task["id"]}.failed.json'
                if failure.exists():failure.unlink()
                completed+=1;line=f'COMPLETE rank={rank} progress={i}/{len(assigned)} kind={c["kind"]} split={c["split"]} task={task["id"]}'
            except Exception:
                failed+=1;detail=traceback.format_exc()
                atomic_json(results/f'{task["id"]}.failed.json',dict(id=task['id'],config=task['config'],status='failed',traceback=detail))
                line=f'FAILED rank={rank} progress={i}/{len(assigned)} task={task["id"]}\n{detail}'
            print(line,file=log);print(line,flush=True)
    atomic_json(base/'workers'/attempt()/f'{rank:03d}.json',dict(rank=rank,world=world,attempt=attempt(),assigned=len(assigned),
                                                            completed=completed,skipped=skipped,failed=failed))
    return int(failed>0)


def report(path):
    from gapslice.guard.compiler import compile_catalog
    from gapslice.guard.profiles import Profile
    m=read_manifest(path);base=ROOT/'outputs/guard'/m['campaign_id']
    rows=[];failed=[];pending=[]
    for t in m['tasks']:
        p=base/'results'/f'{t["id"]}.json'
        if p.exists():
            r=json.loads(p.read_text())
            if r.get('id')!=t['id'] or r.get('campaign_id')!=m['campaign_id'] or r.get('config')!=t['config'] or r.get('status')!='complete' or r.get('stage')!=STAGE:
                raise RuntimeError('Result identity/status mismatch')
            rows.append(r)
        elif p.with_suffix('.failed.json').exists():failed.append(t['id'])
        else:pending.append(t['id'])
    summary=dict(campaign_id=m['campaign_id'],stage=STAGE,preset=m['preset'],expected=len(m['tasks']),
        complete=len(rows),failed=len(failed),pending=len(pending),failed_ids=failed,pending_ids=pending,
        complete_workers=len(list((base/'workers'/attempt()).glob('*.json'))),
        task_cpu_s=sum(r['cpu_s'] for r in rows),
        maximum_process_rss_mib=max((r['process_peak_rss_mib'] for r in rows),default=0),
        generated_utc=datetime.now(timezone.utc).isoformat(),
        limitations='Entirely synthetic research prototype; not final validation or a new stability/safety theorem.')
    atomic_json(base/'summary.json',summary)
    if failed or pending:
        (base/'report.md').write_text('# Incomplete Guard prototype campaign\n\n'+canonical(summary)+'\n')
        print(json.dumps(summary,indent=2));return 1
    main=[r for r in rows if r['config']['kind']=='main']
    profiles={r['config']['profile_id']:Profile(**r['config']['profile']) for r in main}
    domains={}
    for name,envs in m['protocol']['domains'].items():
        selected=[r for r in main if r['config']['environment'] in envs]
        if not selected:raise ValueError('No data for a declared qualification domain')
        domains[name]=compile_catalog(list(profiles.values()),selected,m['protocol']['episode_risk'],
                                     m['protocol']['family_error']/len(m['protocol']['domains']))
    atomic_json(base/'selection.json',dict(domains=domains,protocol=m['protocol'],
        warning='Domain is an externally supplied operating-condition declaration, not an implemented reliable classifier. '
        'Do not mix domain certificates under unknown/misclassified conditions.'))
    ablations=[]
    for kind in ['no_governor','perfect_radio']:
        relevant=[r for r in rows if r['config']['kind']==kind]
        for key in sorted({r['config']['profile_id'] for r in relevant}):
            for env in sorted({r['config']['environment'] for r in relevant}):
                rr=[r for r in relevant if r['config']['profile_id']==key and r['config']['environment']==env]
                if rr:
                    ablations.append(dict(kind=kind,profile=rr[0]['config']['profile'],environment=env,
                        failures=sum(r['metrics']['failures'] for r in rr),episodes=sum(r['metrics']['episodes'] for r in rr),
                        tracking_failures=sum(r['metrics']['tracking_failures'] for r in rr),
                        clearance_failures=sum(r['metrics']['clearance_failures'] for r in rr),
                        completion_failures=sum(r['metrics']['completion_failures'] for r in rr),source_ids=[r['id'] for r in rr]))
    atomic_json(base/'ablations.json',ablations)
    lines=['# GapSlice-Guard exploratory campaign','',
        'This is synthetic prototype evidence. Novelty, NR link calibration, independent validation and final-paper evaluation remain open.','',
        f'Campaign: `{m["campaign_id"]}`. Complete tasks: {len(rows)}. Failed: 0. Pending: 0.','',
        'Primary episode violation: any clearance <2 m, absolute tracking error >5 m, or target-gap completion later than 40 s.',
        'The tolerances and uncertainty distributions are illustrative and require application justification.','',
        'Selections use design and calibration only; test outcomes are read after selection. A requested maneuver can be declined.',
        'Fixed-sequence/Learn-then-Test and exact binomial inference are existing techniques, not new statistical inventions.','',
        '| Declared domain | Target gap | Method | Selected PRB-slots | Worst held-out event fraction |',
        '|---|---:|---|---:|---:|']
    for name,value in domains.items():
        for decision in value['decisions']:
            for method,evaluation in decision['evaluation'].items():
                if evaluation['abstained']:
                    cost=risk='abstain'
                else:
                    cost=str(evaluation['prb_slots']);risk=f'{max(v["event_fraction"] for v in evaluation["test_environments"].values()):.5f}'
                lines.append(f'| {name} | {decision["contract"]["h_target"]} | {method} | {cost} | {risk} |')
    lines+=['','Exact profile, calibration decisions, design ordering, test counts, pointwise test intervals and result IDs: `selection.json`.',
        'Controller ablations: `ablations.json`. Episode-level metrics and counterexamples: `results/*.json`.',
        'The domain declaration is assumed correct. No implemented classifier or distribution-shift guarantee is supplied.',
        'Abstention is not an instantaneous safe switch to ACC; existing-service continuity is outside this prototype admission demo.',
        'The MILP is a small full-information reference; no scalability or universal approximation guarantee is inferred.','']
    (base/'report.md').write_text('\n'.join(lines))
    print(json.dumps(summary,indent=2));print(f'Report: {base/"report.md"}')
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for cmd in ['build','local']:
        q=sub.add_parser(cmd);q.add_argument('--preset',choices=['smoke','pilot'],default='smoke')
        if cmd=='local':q.add_argument('--workers',type=int,default=2)
    for cmd in ['worker','report']:
        q=sub.add_parser(cmd);q.add_argument('--manifest',type=Path,required=True)
    args=p.parse_args()
    if args.command=='build':print(build(args.preset));return 0
    if args.command=='report':return report(args.manifest)
    if args.command=='worker':return worker(args.manifest,int(os.environ.get('SLURM_PROCID',0)),int(os.environ.get('SLURM_NTASKS',1)))
    if args.workers<1:p.error('workers must be positive')
    path=build(args.preset)
    os.environ['GS_OJCS_ATTEMPT']='local-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        statuses=list(pool.map(worker,[path]*args.workers,range(args.workers),[args.workers]*args.workers))
    result=report(path)
    return int(any(statuses) or result)


if __name__=='__main__':sys.exit(main())
