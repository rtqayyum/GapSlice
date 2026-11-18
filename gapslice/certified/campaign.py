"""Frozen-design, resumable CPU study. HPC run orchestrates srun stages.

Use `python -m gapslice.certified.campaign run --preset smoke --local --workers 2`
for an actual local pipeline check. Research is an extensive synthetic study;
no acceptance, superiority or real-road validity is assumed by this program.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import traceback

# Sets single-threaded numerical libraries before their import.
from gapslice.revision.campaign import atomic_json,canonical,sha,fingerprint

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'outputs/cert'
SCHEMA=1
STAGE='conditional_certificates_synthetic_v1'
VECTOR_KEYS=('episode_violation','peak_error_m','minimum_clearance_m','completion_time_s',
    'realized_gain_seconds','successful_gain_seconds','control_effort','jerk_energy','shield_blocks','maximum_packet_age_s')
_SHIELD=None


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def source():
    result=fingerprint(ROOT)
    result['execution']={str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'Batch',
        *sorted((ROOT/'hpc').glob('*.sh')),*sorted((ROOT/'tests').glob('test_certified*.py')),
        ROOT/'docs/CERTIFIED_PROOFS.md']}
    return result


def immutable(path,value):
    if path.exists():
        if canonical(json.loads(path.read_text()))!=canonical(value):raise RuntimeError(f'Immutable artifact differs: {path}')
    else:atomic_json(path,value)
    return path


def make_candidate(profile,policy):
    body=dict(profile=asdict(profile),policy=asdict(policy))
    return dict(id=sha(body)[:20],**body)


def design_bank(preset):
    from gapslice.certified.profiles import Profile,catalog
    from gapslice.certified.simulator import Policy
    if preset=='smoke':
        return [make_candidate(p,Policy()) for p in [
            Profile(n_trucks=3,prbs=0,copies=0,pattern='none',layout='none'),
            Profile(n_trucks=3,layout='serial',prbs=40,copies=2,phase=2)]]
    result=[]
    for n,h,cap,payload in itertools.product([3,5,7],[.6,.8,1.,1.2],[51,106],[300,600,1200]):
        for p in catalog(n,h,cap,payload,broad=True):
            for mode in ['fused','hold','radar']:
                for kp,kd,omega in [(.4,1.4,4.),(.8,1.8,8.),(1.2,2.2,12.)]:
                    result.append(make_candidate(p,Policy(controller=mode,kp=kp,kd=kd,observer_bandwidth=omega)))
    if len({c['id'] for c in result})!=len(result):raise AssertionError('Duplicate candidate')
    return result


def protocol(preset):
    if preset not in {'smoke','research'}:raise ValueError('Unknown preset')
    return dict(schema=SCHEMA,stage=STAGE,preset=preset,
        namespace=f'cert-{preset}-frozen-v1',
        design_n=8 if preset=='smoke' else 64,
        calibration_n=16 if preset=='smoke' else 32768,
        test_n=16 if preset=='smoke' else 32768,
        batch=8 if preset=='smoke' else 2048,
        environments=['nominal'] if preset=='smoke' else ['nominal','correlated','blocked'],
        domains={'nominal':['nominal']} if preset=='smoke' else {'los':['nominal','correlated'],'blocked':['blocked']},
        risk_denominator=1600,risk_units=[1,2,4,8,16],fleet_units=16,
        risk_family_error='1/25',benefit_family_error='1/100',
        screen='Design only: choose one gain tuple per contract/controller; retain best parallel and serial profiles per phase/domain plus radio-free option',
        primary='At 2ms replay checkpoints: |tracking error|>5m or clearance<2m; or reference incomplete by40s; or uncertified initial state',
        reward='Time-average achieved headway reduction, clipped to contract gain and zeroed on primary failure',
        limitations='Synthetic model with bounded sensors and an uncalibrated PHY surrogate. Assumption-conditional clearance proof; no full-system string stability or measured-data validation.')


def make_study(preset):
    from gapslice.certified.safety import Bounds
    bank=design_bank(preset);p=protocol(preset)
    body=dict(protocol=p,source=source(),bounds=asdict(Bounds()),candidate_bank=bank)
    sid=f'cert-{preset}-{sha(body)[:16]}';study=dict(id=sid,**body)
    path=BASE/'studies'/sid/'study.json';immutable(path,study)
    immutable(path.parent/'identity.json',dict(id=sid,source=body['source'],study_sha256=digest(path)))
    return path,study


def read_study(path):
    path=Path(path).resolve()
    if not path.is_relative_to(BASE.resolve()):raise ValueError('Study must be inside project outputs/cert')
    s=json.loads(path.read_text());body={k:s[k] for k in ['protocol','source','bounds','candidate_bank']}
    if s['id']!=f'cert-{s["protocol"]["preset"]}-{sha(body)[:16]}':raise ValueError('Study identity mismatch')
    if s['source']!=source():raise RuntimeError('Source/runtime changed. Preserve old study and start a new one.')
    return s


def task(candidate,env,split,seed,episodes,model,kind='main'):
    c=dict(candidate=candidate,environment=env,split=split,seed=seed,episodes=episodes,
        microbatch=min(128,episodes),model=model,kind=kind)
    return dict(id=sha(c)[:24],config=c)


def replay_tasks(study,bank,split):
    from gapslice.certified.simulator import Model
    p=study['protocol'];n=p[f'{split}_n'];batch=min(n,p['batch']);result=[]
    if n%batch:raise ValueError('Sample count must be divisible by fixed paired batch')
    for candidate,env,index in itertools.product(bank,p['environments'],range(n//batch)):
        result.append(task(candidate,env,split,71001+index,batch,asdict(Model(data_namespace=p['namespace']))))
    return result


def manifest(study_path,study,name,tasks,inputs=None):
    body=dict(schema=SCHEMA,study=study['id'],name=name,tasks=tasks,inputs=inputs or {})
    value=dict(id=sha(body)[:20],**body)
    path=Path(study_path).parent/name/'manifest.json';immutable(path,value)
    return path


def read_manifest(path):
    path=Path(path).resolve()
    if not path.is_relative_to(BASE.resolve()):raise ValueError('Manifest must be inside project outputs/cert')
    m=json.loads(path.read_text());body={k:m[k] for k in ['schema','study','name','tasks','inputs']}
    if m['id']!=sha(body)[:20] or len({t['id'] for t in m['tasks']})!=len(m['tasks']):raise ValueError('Corrupt manifest')
    if any(t['id']!=sha(t['config'])[:24] for t in m['tasks']):raise ValueError('Corrupt task identity')
    return m


def result_path(manifest_path,task_id):return Path(manifest_path).parent/'results'/task_id[:2]/f'{task_id}.json'


def result(manifest_path,item,verify=True):
    path=result_path(manifest_path,item['id'])
    if not path.is_file():return None
    r=json.loads(path.read_text())
    if r['task_id']!=item['id'] or r['config']!=item['config']:raise ValueError('Result identity mismatch')
    data=path.with_suffix('.npz')
    if verify and (not data.is_file() or digest(data)!=r['raw_sha256']):raise RuntimeError(f'Raw result missing or altered: {data}')
    return r


def run_task(manifest_path,item,table_path):
    import numpy as np
    from gapslice.certified.safety import Shield
    from gapslice.certified.simulator import simulate,Policy,Model
    from gapslice.certified.profiles import Profile,allocate
    from gapslice.guard.simulator import ENVIRONMENTS
    global _SHIELD
    if result(manifest_path,item) is not None:return 'RESUME'
    c=item['config'];path=result_path(manifest_path,item['id']);path.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();cpu=time.process_time()
    if c['kind']=='allocation':
        menus={owner:[(Profile(**x['profile']),x['benefit']) for x in menu] for owner,menu in c['menus'].items()}
        output=allocate(menus,c['risk_costs'],method=c['method'],time_limit=30.)
        vectors={'objective':np.array([output['benefit_microseconds']])}
    else:
        if _SHIELD is None:_SHIELD=Shield(table_path,verify_hashes=True)
        candidate=c['candidate'];output=None
        additive=['episodes','failures','tracking_failures','clearance_failures','completion_failures',
            'initial_uncertified','safety_certificate_breaches','observer_bound_breaches','packet_failures']
        # Storage shards are larger than numerical microbatches: this avoids
        # millions of tiny files and large cache-thrashing envelope gathers.
        for index,start in enumerate(range(0,c['episodes'],c['microbatch'])):
            count=min(c['microbatch'],c['episodes']-start)
            current=simulate(Profile(**candidate['profile']),Policy(**candidate['policy']),
                ENVIRONMENTS[c['environment']],c['seed']*100000+index,count,c['split'],_SHIELD,Model(**c['model']))
            if current['first_failure'] is not None:current['first_failure']['episode']+=start
            if output is None:output=current
            else:
                if current['packet_trials_per_episode']!=output['packet_trials_per_episode']:raise AssertionError('Inconsistent source clock')
                for key in VECTOR_KEYS:output[key].extend(current[key])
                for key in additive:output[key]+=current[key]
                if output['first_failure'] is None:output['first_failure']=current['first_failure']
        vectors={key:np.asarray(output.pop(key),dtype=np.uint8 if key=='episode_violation' else float) for key in VECTOR_KEYS}
        if any(len(x)!=c['episodes'] for x in vectors.values()):raise AssertionError('Truncated result vectors')
        rewards=vectors['successful_gain_seconds']
        output['reward_sum']=float(np.sum(rewards,dtype=np.float64))
        output['metric_means']={k:float(np.mean(x[np.isfinite(x)])) if np.isfinite(x).any() else None
            for k,x in vectors.items()}
    # NPZ first, JSON is the commit marker. Preserve orphan data on a retry.
    data=path.with_suffix('.npz')
    if data.exists():data.rename(data.with_name(data.name+f'.orphan-{time.time_ns()}'))
    temporary=data.with_name(data.name+f'.partial-{os.getpid()}')
    with temporary.open('wb') as f:np.savez_compressed(f,**vectors);f.flush();os.fsync(f.fileno())
    os.replace(temporary,data)
    record=dict(task_id=item['id'],config=c,raw_sha256=digest(data),output=output,
        wall_s=time.monotonic()-started,cpu_s=time.process_time()-cpu,
        process_max_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024))
    atomic_json(path,record)
    old=path.with_suffix('.failed.json')
    if old.exists():old.rename(old.with_name(old.name+f'.recovered-{time.time_ns()}'))
    return 'COMPLETE'


def worker(manifest_path,table_path,rank,size):
    global _SHIELD
    try:return _worker(manifest_path,table_path,rank,size)
    finally:
        if _SHIELD is not None:
            _SHIELD.close()
            _SHIELD=None


def _worker(manifest_path,table_path,rank,size):
    m=read_manifest(manifest_path)
    identity=json.loads((Path(manifest_path).parent.parent/'identity.json').read_text())
    if identity['id']!=m['study'] or identity['source']!=source():raise RuntimeError('Worker source/runtime mismatch')
    attempt=os.environ.get('GS_OJCS_ATTEMPT','local')
    log=ROOT/'logs'/m['study']/attempt/m['name'];log.mkdir(parents=True,exist_ok=True)
    # A separate immutable, strided shard per rank; common episode streams are
    # task-defined and do not depend on rank, submission, or process order.
    assigned=m['tasks'][rank::size];failed=0;start=time.monotonic();episodes_done=0;tasks_done=0
    telemetry=Path(manifest_path).parent/'workers'/attempt/f'{rank:03d}.json'
    with (log/f'progress-{rank:03d}.log').open('a',buffering=1) as stream:
        for number,item in enumerate(assigned,1):
            try:status=run_task(manifest_path,item,table_path)
            except Exception:
                failed+=1;status='FAILED';trace=traceback.format_exc()
                atomic_json(result_path(manifest_path,item['id']).with_suffix('.failed.json'),
                    dict(task_id=item['id'],config=item['config'],traceback=trace))
                print(trace,file=sys.stderr,flush=True)
            stream.write(f'{status} rank={rank} progress={number}/{len(assigned)} task={item["id"]} kind={item["config"]["kind"]}\n')
            if not failed:episodes_done+=item['config'].get('episodes',0);tasks_done+=1
            if failed or number%10==0 or number==len(assigned):
                atomic_json(telemetry,dict(rank=rank,assigned=len(assigned),processed=tasks_done,
                    completed_episodes=episodes_done,failed=failed,wall_s=time.monotonic()-start,
                    finished=number==len(assigned) and not failed))
            if failed:break
    atomic_json(Path(manifest_path).parent/'workers'/attempt/f'{rank:03d}.json',
        dict(rank=rank,assigned=len(assigned),processed=tasks_done,completed_episodes=episodes_done,failed=failed,
            finished=tasks_done==len(assigned) and not failed,wall_s=time.monotonic()-start))
    return failed


def execute(path,tables,workers,local):
    m=read_manifest(path);print(f'STAGE {m["name"]} tasks={len(m["tasks"])} workers={workers} manifest={path}',flush=True)
    if local:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            failures=list(pool.map(worker,[str(path)]*workers,[str(tables)]*workers,range(workers),[workers]*workers))
        code=int(any(failures))
    else:
        log=ROOT/'logs'/m['study']/os.environ['GS_OJCS_ATTEMPT']/m['name'];log.mkdir(parents=True,exist_ok=True)
        command=['srun',f'--ntasks={workers}','--cpus-per-task=1','--kill-on-bad-exit=1',
            f'--output={log}/worker_%t.out',f'--error={log}/worker_%t.err',sys.executable,
            '-m','gapslice.certified.campaign','worker','--manifest',str(path),'--tables',str(tables)]
        code=subprocess.run(command,check=False).returncode
    complete=sum(result(path,t) is not None for t in m['tasks'])
    summary=dict(stage=m['name'],expected=len(m['tasks']),complete=complete,failed_or_pending=len(m['tasks'])-complete,
        worker_exit_code=code,manifest=str(path))
    atomic_json(Path(path).parent/'summary.json',summary);print(json.dumps(summary),flush=True)
    if code or complete!=len(m['tasks']):raise RuntimeError(f'Incomplete {m["name"]}; resume same command; completed tasks are retained')


def aggregate(path):
    m=read_manifest(path);cells={}
    for item in m['tasks']:
        r=result(path,item);c=item['config']
        if r is None:raise RuntimeError('Cannot aggregate incomplete stage')
        key=(c['candidate']['id'],c['environment']);v=cells.setdefault(key,dict(n=0,k=0,reward_sum=0.,cpu_s=0.,
            tracking_failures=0,clearance_failures=0,completion_failures=0,initial_uncertified=0,
            safety_certificate_breaches=0,observer_bound_breaches=0,metric_sums={},candidate=c['candidate']))
        o=r['output'];v['n']+=o['episodes'];v['k']+=o['failures'];v['reward_sum']+=o['reward_sum'];v['cpu_s']+=r['cpu_s']
        for name in ['tracking_failures','clearance_failures','completion_failures','initial_uncertified',
            'safety_certificate_breaches','observer_bound_breaches']:v[name]+=o[name]
        for name,mean in o['metric_means'].items():
            # Completion mean conditions on completion; keep per-batch raw
            # values for exact analyses rather than mislabel pooled means.
            if mean is not None and name!='completion_time_s':v['metric_sums'][name]=v['metric_sums'].get(name,0.)+o['episodes']*mean
    return cells


def contract(candidate):
    p=candidate['profile'];return tuple(p[x] for x in ['n_trucks','h_target','cap','payload_bytes'])


def screen(study,design):
    p=study['protocol'];bank=study['candidate_bank']
    if p['preset']=='smoke':return dict(selected=bank,gain_selection=[],design_only=True)
    groups={}
    for candidate in bank:groups.setdefault((contract(candidate),candidate['policy']['controller']),[]).append(candidate)
    selected={};gains=[]
    for (group,mode),candidates in sorted(groups.items()):
        gainscores={}
        for c in candidates:
            policy=c['policy'];gain=tuple(policy[k] for k in ['kp','kd','observer_bandwidth'])
            scores=[design[c['id'],env] for env in p['environments']]
            score=(max(v['k']/v['n'] for v in scores),-min(v['reward_sum']/v['n'] for v in scores))
            gainscores.setdefault(gain,[]).append(score)
        # Every gain gets exactly the same catalog and synthetic seeds.
        best=min(gainscores,key=lambda gain:(sum(x[0] for x in gainscores[gain]),sum(x[1] for x in gainscores[gain]),gain))
        gains.append(dict(contract=group,controller=mode,gain=best))
        tuned=[c for c in candidates if tuple(c['policy'][k] for k in ['kp','kd','observer_bandwidth'])==best]
        for c in tuned:
            if c['profile']['layout']=='none':selected[c['id']]=c
        for domain,envs in p['domains'].items():
            for phase in [0,2,4,6,8]:
                choices=[c for c in tuned if c['profile']['layout']!='none' and c['profile']['phase']==phase]
                def order(c):
                    values=[design[c['id'],e] for e in envs];q=c['profile']
                    return (max(v['k']/v['n'] for v in values),-min(v['reward_sum']/v['n'] for v in values),
                        3*(q['n_trucks']-1)*q['copies']*q['prbs'],c['id'])
                for layout in ['parallel','serial']:
                    bylayout=[c for c in choices if c['profile']['layout']==layout]
                    for c in sorted(bylayout,key=order)[:1]:selected[c['id']]=c
    return dict(selected=sorted(selected.values(),key=lambda c:c['id']),gain_selection=gains,design_only=True,
        qualification_data_used=False,design_manifest_hash=None)


def qualification(study,selected,cells):
    from gapslice.certified.risk import RISK_UNITS,critical_count,benefit_lower
    p=study['protocol'];tests=len(selected)*len(p['environments'])*len(RISK_UNITS)
    benefit_tests=len(selected)*len(p['environments']);records=[];n=p['calibration_n']
    critical={str(u):critical_count(n,u,tests) for u in RISK_UNITS}
    for c in selected:
        for domain,envs in p['domains'].items():
            good=[u for u in RISK_UNITS if all(cells[c['id'],e]['k']<=critical[str(u)] for e in envs)]
            maximum=c['profile']['h_initial']-c['profile']['h_target']
            lower=min(benefit_lower(cells[c['id'],e]['reward_sum'],n,maximum,benefit_tests) for e in envs)
            records.append(dict(candidate=c,domain=domain,qualified=bool(good),risk_units=min(good) if good else None,
                benefit_lower_s=lower,benefit_microseconds=math.floor(1e6*lower),
                environment_failures={e:cells[c['id'],e]['k'] for e in envs},n_per_environment=n))
    return dict(risk_tests=tests,benefit_tests=benefit_tests,exact_critical_counts=critical,records=records,
        procedure='Exact rational binomial lower-tail test + Bonferroni; bounded-reward Hoeffding LCB; no test outcomes used')


def allocation_tasks(study,qualified):
    p=study['protocol'];records=qualified['records'];tasks=[]
    for cap,domain,tenants in itertools.product([51] if p['preset']=='smoke' else [51,106],p['domains'],[4] if p['preset']=='smoke' else [4,8,16,32]):
        for variant in ['fused','hold','radar','fused_parallel','fused_synchronous']:
            mode=variant.split('_')[0];menus={};risks={}
            for i in range(tenants):
                n=3 if p['preset']=='smoke' else [3,5,7][i%3]
                payload=300 if p['preset']=='smoke' else [300,600,1200][(i//3)%3]
                choices=[]
                for r in records:
                    c=r['candidate'];q=c['profile']
                    if not (r['qualified'] and r['domain']==domain and q['cap']==cap and q['n_trucks']==n
                            and q['payload_bytes']==payload and c['policy']['controller']==mode):continue
                    if variant=='fused_parallel' and q['layout'] not in {'parallel','none'}:continue
                    if variant=='fused_synchronous' and q['phase']!=0:continue
                    from gapslice.certified.profiles import Profile
                    profile=Profile(**q)
                    risks[profile.key]=r['risk_units'];choices.append(dict(profile=q,benefit=r['benefit_microseconds']))
                menus[str(i)]=choices
            for method in ['greedy','exact']:
                c=dict(kind='allocation',menus=menus,risk_costs=risks,method=method,cap=cap,domain=domain,tenants=tenants,variant=variant)
                tasks.append(dict(id=sha(c)[:24],config=c))
    return tasks


def diagnostic_tasks(study,selected,qualified,calibration):
    from gapslice.certified.simulator import Model
    p=study['protocol'];chosen={};result_tasks=[]
    # Pick one by calibration only per contract/controller/domain; selection
    # is explicit. Test/ablation data never change the proposed policy.
    for r in qualified['records']:
        c=r['candidate'];key=(contract(c),c['policy']['controller'],r['domain'])
        def order(x):return (not x['qualified'],-x['benefit_lower_s'],x['candidate']['id'])
        if key not in chosen or order(r)<order(chosen[key]):chosen[key]=r
    for r in chosen.values():
        c=r['candidate']
        for env in p['domains'][r['domain']]:
            count=8 if p['preset']=='smoke' else 2048;batch=min(p['batch'],count)
            for index in range(count//batch):
                seed=71001+index;base=Model(data_namespace=p['namespace'])
                nofilter=dict(c,policy=dict(c['policy'],shield=False));nofilter['id']=sha(dict(profile=nofilter['profile'],policy=nofilter['policy']))[:20]
                variants=[('no_shield',nofilter,base),('perfect_radio',c,replace(base,radio_mode='perfect')),
                    ('slow_hard',c,replace(base,eta_mode='slow',brake_mode='hard',initial_speed_mps=30.)),
                    ('alternating_hard',c,replace(base,eta_mode='alternating',brake_mode='hard',initial_speed_mps=60/3.6))]
                for kind,cc,model in variants:result_tasks.append(task(cc,env,'test',seed,batch,asdict(model),kind))
    # Deduplicate when domains select the same candidate/environment.
    return sorted({t['id']:t for t in result_tasks}.values(),key=lambda t:t['id'])


def report(study_path,study,selection,qualification_value,stages,proof):
    from gapslice.certified.risk import cp_upper
    base=Path(study_path).parent;cells=aggregate(stages['test']);rows=[]
    for (cid,env),v in sorted(cells.items()):
        rows.append(dict(candidate_id=cid,environment=env,**{k:x for k,x in v.items() if k!='candidate'},
            descriptive_cp95_upper=cp_upper(v['k'],v['n']),empirical_risk=v['k']/v['n']))
    immutable(base/'heldout_cells.json',rows)
    allocations=[result(stages['allocation'],t)['output']|{'scenario':t['config']} for t in read_manifest(stages['allocation'])['tasks']]
    # Menus already live in immutable task manifests; keep final bundle compact.
    for item in allocations:item['scenario'].pop('menus',None);item['scenario'].pop('risk_costs',None)
    atomic_json(base/'allocations.json',allocations)
    diagnostics=[]
    for t in read_manifest(stages['diagnostics'])['tasks']:
        r=result(stages['diagnostics'],t)
        diagnostics.append(dict(task_id=t['id'],config=t['config'],output=r['output']))
    atomic_json(base/'diagnostics.json',diagnostics)
    summary=dict(study_id=study['id'],stage=STAGE,preset=study['protocol']['preset'],
        design_candidates=len(study['candidate_bank']),frozen_candidates=len(selection['selected']),
        qualified_domain_records=sum(r['qualified'] for r in qualification_value['records']),
        risk_tests=qualification_value['risk_tests'],critical_counts=qualification_value['exact_critical_counts'],
        completed_stages={name:json.loads((Path(path).parent/'summary.json').read_text()) for name,path in stages.items()},
        heldout_episodes=sum(x['n'] for x in rows),heldout_failures=sum(x['k'] for x in rows),
        safety_certificate_breaches=sum(x['safety_certificate_breaches'] for x in rows),
        observer_bound_breaches=sum(x['observer_bound_breaches'] for x in rows),
        heldout_cell_count=len(rows),proof_check=proof,limitations=study['protocol']['limitations'])
    atomic_json(base/'summary.json',summary)
    lines=[f'# {study["id"]}', '', 'Full synthetic redesign: bounded-sensing backup safety, predictive control, exact finite-family risk qualification and cyclic multi-tenant scheduling.',
        '', f'Design candidates: {summary["design_candidates"]}; frozen candidates: {summary["frozen_candidates"]}; qualified contract/domain records: {summary["qualified_domain_records"]}.',
        f'Held-out episodes: {summary["heldout_episodes"]}; failures: {summary["heldout_failures"]}. These totals mix contracts and are not a common population risk estimate.',
        f'Clearance certificate breaches: {summary["safety_certificate_breaches"]}; observer-bound breaches: {summary["observer_bound_breaches"]}.',
        '', 'Exact binomial critical counts: '+json.dumps(summary['critical_counts']),
        '', '## Interpretation', '',
        'Qualification and allocation use calibration only. Held-out outcomes are descriptive independent checks and never revise the frozen candidate bank. Multiple contracts share traces intentionally; the union-bound risk procedure does not require independence across candidates. Episodes within a cell use separate pseudorandom streams.',
        'The full closed-loop safety claim is conditional on the braking-model/sensor/entry assumptions in docs/CERTIFIED_PROOFS.md. The nominal Lyapunov identity is conditional on ideal unsaturated error dynamics. Neither establishes uniform string stability. Radio and traffic distributions are synthetic.',
        'A zero-qualified result is valid and must be reported. Gains relative to hold/radar/phase/layout baselines must be read from allocations and individual held-out cells; superiority is not assumed. The old Guard v1 has a different plant/sensor model and is not a matched comparator.',
        '', '## Artifacts', '', 'study.json: complete frozen protocol/source/runtime/candidate bank.',
        'selection.json: design-only candidate selection and gains.', 'qualification.json: exact risk labels and conservative achieved-benefit bounds.',
        'heldout_cells.json: independent test counts and descriptive confidence bounds.',
        'allocations.json: fair common-model comparisons, independent integer bounds, admitted reservations.',
        'proof_checks.json: independent numerical falsification checks and Lyapunov witness.',
        'Each stage retains manifest.json, results/*.json and results/*.npz, workers/JOB/*.json, summary.json.',
        '', '## Remaining publication work', '',
        'Measured NR/channel calibration or a separately implemented external co-simulator; broader literature comparison with faithful published baselines; assumption sensitivity and engineering validation; theorem peer review; a manuscript written around observed results. No journal acceptance or ranking is guaranteed.']
    (base/'report.md').write_text('\n'.join(lines)+'\n')
    from gapslice.certified.plots import create
    create(base,study,rows,qualification_value,allocations)
    # Small artifact bundle for analysis; preserve all episode vectors on HPC.
    import tarfile
    bundle=base/'analysis_bundle.tar.gz'
    with tarfile.open(bundle,'w:gz') as archive:
        for name in ['study.json','selection.json','qualification.json','heldout_cells.json','allocations.json','diagnostics.json','summary.json','report.md','proof_checks.json','study_overview.png','study_overview.svg']:
            archive.add(base/name,arcname=f'{study["id"]}/{name}',recursive=False)
    print(json.dumps(summary,indent=2));print(f'REPORT {base}/report.md\nBUNDLE {bundle}',flush=True)


def run(preset,workers,local):
    from gapslice.certified.safety import ensure_tables,Bounds
    from gapslice.certified.verification import verify
    study_path,study=make_study(preset);base=study_path.parent
    BASE.mkdir(parents=True,exist_ok=True);(BASE/'last_study.txt').write_text(str(base)+'\n')
    if not local:
        (BASE/'jobs').mkdir(exist_ok=True);(BASE/'jobs'/f'{os.environ["SLURM_JOB_ID"]}.study').write_text(str(base)+'\n')
    tables=ensure_tables(BASE/'proofs',Bounds(**study['bounds']))
    proof=verify(tables);atomic_json(base/'proof_checks.json',proof)
    stages={}
    stages['design']=manifest(study_path,study,'design',replay_tasks(study,study['candidate_bank'],'design'))
    execute(stages['design'],tables,workers,local)
    design=aggregate(stages['design']);selection=screen(study,design)
    selection['design_manifest_hash']=digest(stages['design']);immutable(base/'selection.json',selection)
    selected=selection['selected'];print(f'FROZEN candidates={len(selected)} using design data only',flush=True)
    for split in ['calibration','test']:
        stages[split]=manifest(study_path,study,split,replay_tasks(study,selected,split),{'selection_sha256':digest(base/'selection.json')})
        execute(stages[split],tables,workers,local)
        if split=='calibration':
            calibration=aggregate(stages[split]);qualified=qualification(study,selected,calibration)
            immutable(base/'qualification.json',qualified)
    stages['diagnostics']=manifest(study_path,study,'diagnostics',diagnostic_tasks(study,selected,qualified,calibration),{'qualification_sha256':digest(base/'qualification.json')})
    execute(stages['diagnostics'],tables,workers,local)
    stages['allocation']=manifest(study_path,study,'allocation',allocation_tasks(study,qualified),{'qualification_sha256':digest(base/'qualification.json')})
    execute(stages['allocation'],tables,workers,local)
    report(study_path,study,selection,qualified,stages,proof)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('run');p.add_argument('--preset',choices=['smoke','research'],required=True);p.add_argument('--local',action='store_true');p.add_argument('--workers',type=int,default=int(os.environ.get('SLURM_NTASKS','2')))
    p=sub.add_parser('worker');p.add_argument('--manifest',required=True);p.add_argument('--tables',required=True)
    a=parser.parse_args()
    if a.command=='run':
        if a.workers<1:parser.error('Positive worker count required')
        run(a.preset,a.workers,a.local)
    else:
        sys.exit(int(worker(a.manifest,a.tables,int(os.environ['SLURM_PROCID']),int(os.environ['SLURM_NTASKS']))>0))


if __name__=='__main__':main()
