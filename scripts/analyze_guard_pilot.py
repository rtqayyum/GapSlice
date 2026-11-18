#!/usr/bin/env python3
"""Read-only analysis of an exported Guard pilot; no physical episodes rerun.

The report narrative is frozen for pilot 3098556; adapt it explicitly for a
different study rather than reusing its numerical prose. The export includes
the original manifest and git commit ID. Fingerprinted
files are compared to that Git snapshot, allowing the current monitor/runtime
to differ. Scientific modules used to replay selection must still match the
recorded source. Raw evidence remains unchanged. Internal checks are not an
independent attestation of where the supplied experiment ran.
"""
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

import numpy as np
from scipy.stats import beta, binom

FROZEN_PILOT='guard-pilot-3915091fe85a87dc'


def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def check_record(r):
    """Verify all per-episode outcomes against the predeclared joint event."""
    c,v=r['config'],r['metrics'];n=c['episodes']
    if not isinstance(n,int) or n<1 or v['episodes']!=n:
        raise ValueError('Episode-count mismatch')
    names=['episode_violation','peak_error_m','minimum_clearance_m',
           'maximum_packet_age_s','episode_packet_loss_fraction','completion_time_s']
    if any(len(v[k])!=n for k in names):raise ValueError('Episode-vector length mismatch')
    canonical(r)
    if any(x not in [0,1] for x in v['episode_violation']):raise ValueError('Nonbinary joint outcome')
    error=np.asarray(v['peak_error_m'])>c['model']['maximum_tracking_error_m']
    clearance=np.asarray(v['minimum_clearance_m'])<c['model']['minimum_clearance_m']
    completion=np.array([x is None for x in v['completion_time_s']])
    if not np.array_equal(v['episode_violation'],error|clearance|completion):
        raise ValueError('Joint outcome disagrees with component events')
    checks=dict(failures=int((error|clearance|completion).sum()),tracking_failures=int(error.sum()),
                clearance_failures=int(clearance.sum()),completion_failures=int(completion.sum()),
                observed_nonpositive_clearance=int((np.asarray(v['minimum_clearance_m'])<=0).sum()))
    if any(v[k]!=expected for k,expected in checks.items()):raise ValueError('Event-count mismatch')
    if any(x<0 or x>1 for x in v['episode_packet_loss_fraction']):raise ValueError('Invalid packet loss')
    trials=v['packet_trials_per_episode']
    if trials<1 or round(sum(v['episode_packet_loss_fraction'])*trials)!=v['packet_failures']:
        raise ValueError('Packet accounting mismatch')
    if any(x is not None and not 0<=x<=c['model']['horizon_s'] for x in v['completion_time_s']):
        raise ValueError('Completion time outside episode')


def load_export(export,campaign,repo):
    if not re.fullmatch(r'guard-pilot-[0-9a-f]{16}',campaign):raise ValueError('Expected a pilot campaign ID')
    base=export/'outputs/guard'/campaign
    path=export/'outputs/guard/manifests'/f'{campaign}.json'
    m=json.loads(path.read_text())
    header={k:m[k] for k in ['schema','stage','preset','configs','protocol','fingerprint']}
    if (m['schema']!=1 or m['stage']!='research_prototype_synthetic' or m['preset']!='pilot'
            or campaign!=f'guard-pilot-{digest(header)[:16]}' or m['campaign_id']!=campaign):
        raise ValueError('Manifest schema/stage/identity mismatch')
    tasks={t['id']:t for t in m['tasks']}
    if (len(tasks)!=len(m['tasks']) or m['configs']!=[t['config'] for t in m['tasks']]
            or any(k!=digest(v['config'])[:20] for k,v in tasks.items())):
        raise ValueError('Task identity/configuration mismatch')
    commits=list((export/'outputs/guard').glob('source-commit-*.txt'))
    if len(commits)!=1:raise ValueError('Require one exported source-commit record')
    commit=commits[0].read_text().strip()
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Invalid source commit')
    checked=0;current_scientific=[]
    for category in ['files','execution_files']:
        for name,expected in m['fingerprint'][category].items():
            rel=PurePosixPath(name)
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe fingerprint path')
            content=subprocess.run(['git','show',f'{commit}:{name}'],cwd=repo,check=True,capture_output=True).stdout
            if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('Git source/input mismatch: '+name)
            checked+=1
            if name.startswith('gapslice/'):
                p=repo/name
                if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
                    raise ValueError('Current scientific source differs; use original checkout: '+name)
                current_scientific.append(name)
    if {p.name for p in (base/'results').glob('*.json')}!={f'{k}.json' for k in tasks}:
        raise ValueError('Missing, extra or failed result records')
    records=[]
    for key,task in tasks.items():
        r=json.loads((base/'results'/f'{key}.json').read_text())
        if (r['id']!=key or r['campaign_id']!=campaign or r['config']!=task['config']
                or r['status']!='complete' or r['stage']!=m['stage']):
            raise ValueError('Result identity/status mismatch')
        if digest(r['config']['profile'])[:20]!=r['config']['profile_id']:
            raise ValueError('Profile identity mismatch')
        check_record(r);records.append(r)
    summary=json.loads((base/'summary.json').read_text())
    if (summary['campaign_id']!=campaign or summary['expected']!=len(tasks) or summary['complete']!=len(records)
            or summary['failed'] or summary['pending']):raise ValueError('Summary completeness mismatch')
    if not math.isclose(summary['task_cpu_s'],sum(r['cpu_s'] for r in records),abs_tol=1e-6):
        raise ValueError('CPU summary mismatch')
    if not math.isclose(summary['maximum_process_rss_mib'],max(r['process_peak_rss_mib'] for r in records),abs_tol=1e-6):
        raise ValueError('Memory summary mismatch')
    job=commits[0].stem.removeprefix('source-commit-')
    workers=[json.loads(p.read_text()) for p in (base/'workers'/job).glob('*.json')]
    ranks={r['rank'] for r in records}
    if (len(workers)!=summary['complete_workers'] or {w['rank'] for w in workers}!=ranks
            or any(w['failed'] or w['completed']+w['skipped']!=w['assigned'] for w in workers)):
        raise ValueError('Worker completion mismatch')
    verification=dict(campaign_id=campaign,job_id=job,source_commit=commit,source_hashes_checked=checked,
        current_scientific_files_checked=len(current_scientific),records=len(records),
        episode_replays=sum(r['config']['episodes'] for r in records),worker_records=len(workers),
        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),result_content_digest=digest(records),
        analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        hosts=dict(Counter(r['hostname'] for r in records)),
        scope='Internal provenance/accounting checks against the supplied export; not external attestation')
    return m,records,summary,verification,base


def close(a,b):
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(close(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(close(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-14)
    return a==b


def verify_selection(m,records,selection,repo):
    sys.path.insert(0,str(repo))
    from gapslice.guard.compiler import compile_catalog
    from gapslice.guard.profiles import Profile
    from gapslice.revision.slot_schedule import validate
    main=[r for r in records if r['config']['kind']=='main']
    profiles={r['config']['profile_id']:Profile(**r['config']['profile']) for r in main}
    checks=[]
    for domain,envs in m['protocol']['domains'].items():
        expected=compile_catalog(list(profiles.values()),[r for r in main if r['config']['environment'] in envs],
                                 m['protocol']['episode_risk'],m['protocol']['family_error']/len(m['protocol']['domains']))
        stored=selection['domains'][domain]
        # MILP can choose a different tied allocation. Match selection and
        # qualification fully, then check stored allocations independently.
        if not close({k:v for k,v in expected.items() if k!='admission'},
                     {k:v for k,v in stored.items() if k!='admission'}):
            raise ValueError('Frozen selection/qualification replay differs')
        for method,methods in stored['admission'].items():
            costs={k:r for d in stored['decisions'] for k,r in d['risk_frontiers'][method].items()}
            for mode in ['greedy','exact']:
                a=methods[mode];placements=[];owners=[];risk=0.;utility=0.;resource=0
                for col in a['allocation']:
                    p=profiles[col['profile']];p.check();owner=col['tenant'];owners.append(owner)
                    if col['profile'] not in costs or col['risk_cost']!=costs[col['profile']]:
                        raise ValueError('Admission uses an unavailable risk label')
                    weight=[.7,.9,1.1,1.3][int(owner.split('-')[-1])]
                    utility+=weight*(np.exp(-p.h_target/.8)-np.exp(-2.8/.8))
                    placements.extend(p.placements(owner,col['frequency_offset']))
                    risk+=col['risk_cost'];resource+=p.cost
                if (len(set(owners))!=len(owners) or len(owners)!=a['admitted'] or
                        validate(placements,next(iter(profiles.values())).cap,[p.job for p in placements]) or
                        risk>a['fleet_risk_budget']+1e-12 or not math.isclose(risk,a['declared_risk_spent'],abs_tol=1e-12)
                        or not math.isclose(utility,a['utility'],abs_tol=1e-12) or resource!=a['total_prb_slots']):
                    raise ValueError('Stored global allocation failed independent checking')
                if not close(expected['admission'][method][mode]['utility'],a['utility']):
                    raise ValueError('Replayed admission objective differs')
                checks.append(dict(domain=domain,method=method,mode=mode,admitted=a['admitted'],valid=True))
    return checks


def interval(k,n,alpha=.05):
    return [0. if k==0 else float(beta.ppf(alpha/2,k,n-k+1)),
            1. if k==n else float(beta.ppf(1-alpha/2,k+1,n-k))]


def grouped(records):
    groups=defaultdict(list)
    for r in records:
        c=r['config'];groups[c['kind'],c['profile_id'],c['environment'],c['split']].append(r)
    return {key:sorted(value,key=lambda r:r['config']['seed']) for key,value in groups.items()}


def cell(key,rows):
    kind,profile,env,split=key
    n=sum(r['metrics']['episodes'] for r in rows);k=sum(r['metrics']['failures'] for r in rows)
    completion=[v for r in rows for v in r['metrics']['completion_time_s'] if v is not None]
    return dict(kind=kind,profile_id=profile,environment=env,split=split,profile=rows[0]['config']['profile'],
        episodes=n,failures=k,event_fraction=k/n,pointwise_exact_95=interval(k,n),
        **{name:sum(r['metrics'][name] for r in rows) for name in
           ['tracking_failures','clearance_failures','completion_failures','observed_nonpositive_clearance']},
        mean_packet_loss=float(np.mean([v for r in rows for v in r['metrics']['episode_packet_loss_fraction']])),
        mean_peak_error_m=float(np.mean([v for r in rows for v in r['metrics']['peak_error_m']])),
        conditional_completion_quantiles_s=None if not completion else np.quantile(completion,[.5,.95,.99]).tolist(),
        completed=len(completion),source_ids=[r['id'] for r in rows])


def paired_effect(left,right):
    if [r['config']['seed'] for r in left]!=[r['config']['seed'] for r in right]:raise ValueError('Unpaired seed batches')
    seed_means=[];n=left_only=right_only=0
    for a,b in zip(left,right):
        x=np.asarray(a['metrics']['episode_violation']);y=np.asarray(b['metrics']['episode_violation'])
        if x.shape!=y.shape:raise ValueError('Unpaired episode vectors')
        seed_means.append(float((x-y).mean()));n+=len(x)
        left_only+=int(((x==1)&(y==0)).sum());right_only+=int(((x==0)&(y==1)).sum())
    # A seed-t interval degenerates when all observed differences are 0/1.
    # Instead bound both discordance probabilities with 97.5% exact intervals;
    # a union bound gives a conservative 95% interval for their difference.
    left_interval=interval(left_only,n,.025);right_interval=interval(right_only,n,.025)
    difference=[max(-1.,left_interval[0]-right_interval[1]),min(1.,left_interval[1]-right_interval[0])]
    return dict(direction='left minus right',episodes=n,seed_means=seed_means,mean=(left_only-right_only)/n,
        conservative_paired_exact_95=difference,left_only=left_only,right_only=right_only,
        scope='Iid paired episodes within this cell; exact discordance bounds, pointwise and unadjusted across comparisons')


def power(n,delta,alternative,alpha):
    lo,hi=-1,n+1
    while hi-lo>1:
        mid=(lo+hi)//2
        if binom.cdf(mid,n,delta)<=alpha:lo=mid
        else:hi=mid
    return dict(n=n,delta=delta,assumed_true_risk=alternative,alpha=alpha,
                largest_accepted_failure_count=lo,power=float(binom.cdf(lo,n,alternative)))


def analyze(m,records,summary,verification,selection):
    groups=grouped(records);cells=[cell(k,v) for k,v in sorted(groups.items())]
    matched=[]
    for key,rows in groups.items():
        kind,pid,env,split=key;p=rows[0]['config']['profile']
        if kind!='main' or split!='test' or p['prbs']!=20 or p['copies']!=4 or p['pattern']!='hopped':continue
        raw_pid=digest({**p,'governor':False})[:20]
        raw=groups['no_governor',raw_pid,env,'test']
        x=np.array([v for r in rows for v in r['metrics']['peak_error_m']])>5
        z=np.array([v is None for r in rows for v in r['metrics']['completion_time_s']])
        matched.append(dict(target=p['h_target'],environment=env,
            governed=cell(key,rows),unguarded=cell(('no_governor',raw_pid,env,'test'),raw),
            raw_minus_governed=paired_effect(raw,rows),
            disjoint_governed_events=dict(tracking_only=int((x&~z).sum()),completion_only=int((z&~x).sum()),
                tracking_and_completion=int((x&z).sum())),
            witness=next((r['metrics']['first_failure'] for r in rows if r['metrics']['first_failure']),None)))
    ranks=[]
    for rank in sorted({r['rank'] for r in records}):
        rs=[r for r in records if r['rank']==rank]
        ranks.append(dict(rank=rank,cpu_s=sum(r['cpu_s'] for r in rs),wall_s=sum(r['wall_s'] for r in rs),tasks=len(rs)))
    first_slot=[]
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from gapslice.guard.profiles import Profile
    for domain,value in selection['domains'].items():
        for method,a in value['admission'].items():
            keys={k for d in value['decisions'] for k in d['risk_frontiers'][method]}
            offered=[Profile(**value['profiles'][key]) for key in keys]
            if offered:
                occupancy=[len({rb for slot,rb in p.cells() if slot==0}) for p in offered]
                first_slot.append(dict(domain=domain,method=method,offered_profiles=len(offered),
                    minimum_first_slot_prbs=min(occupancy),cap=offered[0].cap,
                    first_slot_cardinality_bound=offered[0].cap//min(occupancy),
                    caveat='Bound applies to these synchronized, offered fixed-phase templates only'))
    guard_test=[]
    for domain,value in selection['domains'].items():
        for d in value['decisions']:
            e=d['evaluation']['guard']
            if not e['abstained']:
                envs=e['test_environments'];alpha=.05/len(envs)
                guard_test.append(dict(domain=domain,target=d['contract']['h_target'],profile=e['profile'],
                    changed_gap=e['profile']['h_initial']!=e['profile']['h_target'],
                    environments={name:dict(failures=v['failures'],episodes=v['episodes'],
                        one_sided_upper_bonferroni_environments=float(beta.ppf(1-alpha,v['failures']+1,v['episodes']-v['failures'])))
                                  for name,v in envs.items()}))
    return dict(verification=verification,summary=summary,selection=selection,cells=cells,matched=matched,
        first_slot_bounds=first_slot,qualified_guard_test=guard_test,ranks=ranks,
        cpu_by_kind={kind:sum(r['cpu_s'] for r in records if r['config']['kind']==kind)
                     for kind in sorted({r['config']['kind'] for r in records})},
        calibration_power_sensitivity=[power(n,.01,alt,.05/6) for alt in [.004,.0065,.008]
                                      for n in [2048,4096,8192,16384]],
        limitations='Synthetic exploratory pilot. Test has now been inspected and cannot be reused as fresh '
        'confirmation after redesign. Internal baselines are not published state-of-the-art reproductions. '
        'No measured/testbed evidence, general safety/string-stability result or demonstrated broad superiority.')


def write_figure(data,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,2,figsize=(12,8.8),layout='constrained')
    ax=axes[0,0];matrix=np.zeros((2,3))
    for i,domain in enumerate(['los','blocked']):
        for j,d in enumerate(data['selection']['domains'][domain]['decisions']):
            matrix[i,j]=not d['evaluation']['guard']['abstained']
    ax.imshow(matrix,vmin=0,vmax=1,cmap='Blues',aspect='auto')
    for i in range(2):
        for j in range(3):ax.text(j,i,'Qualified\nsteady gap' if matrix[i,j] else 'Abstain',ha='center',va='center',color='white' if matrix[i,j] else '#243d4b')
    ax.set(xticks=[0,1,2],xticklabels=['0.6 s','1.0 s','1.5 s'],yticks=[0,1],yticklabels=['LOS domain','Blocked'],
           xlabel='Requested headway',title='A. Guard qualifies 1 of 6 cases')
    ax=axes[0,1]
    cells=[c for c in data['cells'] if c['kind']=='main' and c['split']=='test' and c['environment']=='correlated' and c['profile']['h_target']==1.5]
    for copies,color in [(1,'#71818b'),(2,'#b57434'),(4,'#007f8b')]:
        cc=[c for c in cells if c['profile']['copies']==copies]
        ax.scatter([4*c['profile']['prbs']*copies for c in cc],[100*c['event_fraction'] for c in cc],s=50,color=color,label=f'{copies} copies')
    ax.axhline(1.,color='#aa4444',ls='--',lw=1,label='1% target')
    ax.annotate('Empirical choice\n43/2048',xy=(80,100*43/2048),xytext=(105,5),arrowprops={'arrowstyle':'-','color':'#777'},fontsize=9)
    ax.annotate('Guard = max-resource choice\n8/2048',xy=(320,100*8/2048),xytext=(150,.18),arrowprops={'arrowstyle':'-','color':'#777'},fontsize=9)
    ax.set(yscale='log',xlabel='PRB-slots per packet period (all four links)',ylabel='Held-out episode violation (%)',
           title='B. Correlated channel, steady 1.5 s gap',ylim=(.1,100))
    ax.legend(fontsize=8,loc='upper right')
    ax=axes[1,0]
    selected=sorted([m for m in data['matched'] if m['environment']=='correlated'],key=lambda m:m['target'])
    for name,label,color,shift in [('unguarded','Fixed six-second ramp','#cb673a',-.05),('governed','Local governor','#007f8b',.05)]:
        vals=[100*m[name]['event_fraction'] for m in selected]
        err=[[100*(m[name]['event_fraction']-m[name]['pointwise_exact_95'][0]) for m in selected],
             [100*(m[name]['pointwise_exact_95'][1]-m[name]['event_fraction']) for m in selected]]
        ax.errorbar(np.arange(3)+shift,vals,yerr=err,marker='o',capsize=3,color=color,label=label)
    ax.axhline(1.,ls='--',color='#aa4444',lw=1)
    ax.set(xticks=np.arange(3),xticklabels=['0.6 s','1.0 s','1.5 s'],yscale='log',ylim=(.1,130),
           xlabel='Requested headway',ylabel='Held-out episode violation (%)',title='C. Governor ablation, identical hopped radio')
    ax.legend(fontsize=9)
    ax=axes[1,1];selected=sorted([m for m in data['matched'] if m['environment']=='blocked'],key=lambda m:m['target'])
    bottom=np.zeros(3)
    for key,label,color in [('tracking_only','Tracking only','#cb673a'),('completion_only','Completion only','#c1a33f'),('tracking_and_completion','Both','#66759d')]:
        v=np.array([100*m['disjoint_governed_events'][key]/m['governed']['episodes'] for m in selected])
        ax.bar(np.arange(3),v,bottom=bottom,color=color,label=label);bottom+=v
    ax.axhline(1.,ls='--',color='#aa4444',lw=1)
    ax.set(xticks=np.arange(3),xticklabels=['0.6 s','1.0 s','1.5 s'],xlabel='Requested headway',
           ylabel='Held-out episode violation (%)',ylim=(0,50),title='D. Blocked-link failures remain substantial')
    ax.legend(fontsize=9)
    fig.suptitle('Guard pilot 3098556 · synthetic exploratory evidence',fontsize=15)
    for ext in ['png','svg']:fig.savefig(output/f'guard_pilot_findings.{ext}',dpi=180)
    plt.close(fig)


def report(data,output):
    def table(headers,rows):
        return '<table><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr>'+''.join(
            '<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</table>'
    selection_rows=[]
    for name,d in data['selection']['domains'].items():
        for c in d['decisions']:
            for method,e in c['evaluation'].items():
                selection_rows.append([name,c['contract']['h_target'],method,
                    'abstain' if e['abstained'] else e['prb_slots'],
                    '—' if e['abstained'] else f'{100*max(v["event_fraction"] for v in e["test_environments"].values()):.3f}%'])
    ablation_rows=[]
    for m in sorted(data['matched'],key=lambda x:(x['environment'],x['target'])):
        a,b=m['unguarded'],m['governed'];completion=b['conditional_completion_quantiles_s']
        ablation_rows.append([m['environment'],m['target'],f'{a["failures"]}/{a["episodes"]}',f'{b["failures"]}/{b["episodes"]}',
            b['clearance_failures'],b['completion_failures'],'—' if completion is None else f'{completion[0]:.2f} / {completion[1]:.2f}'])
    image_data=base64.b64encode((output/'guard_pilot_findings.png').read_bytes()).decode()
    content=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Guard pilot analysis</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#203642;max-width:1140px;margin:40px auto;padding:0 24px}}
h1,h2{{line-height:1.25}}h2{{margin-top:2em}}table{{border-collapse:collapse;width:100%;font-size:14px;margin:20px 0}}
td,th{{text-align:left;padding:8px;border-bottom:1px solid #d2dbdf}}th{{background:#eef3f5}}img{{width:100%}}
.note{{border-left:4px solid #be673c;background:#fff6ef;padding:14px}}code{{overflow-wrap:anywhere}}</style>
<h1>Guard pilot: a useful governor, an insufficient overall method</h1>
<p>Job {data['verification']['job_id']} · {data['verification']['campaign_id']} · analysis {datetime.now(timezone.utc).isoformat()}</p>
<p class="note">The pilot does not yet establish the requested performance or journal-quality contribution.
Guard qualifies only the LOS 1.5 s case, which requires no headway change, and selects exactly the same
320-PRB-slot profile as the generous-resource baseline. No resource saving or broader multi-tenant admission
advantage is demonstrated. The governor itself shows a large, matched reduction in maneuver violations.</p>
<p>Checked {data['verification']['records']:,} result identities and episode-vector accounting,
{data['verification']['episode_replays']:,} episode replays and {data['verification']['source_hashes_checked']}
source/input/execution hashes against Git commit <code>{data['verification']['source_commit']}</code>.
Replayed selection/qualification and independently checked all stored admission schedules and risk sums.
These are internal consistency checks, not external authentication or independent physical validation.</p>
<img src="data:image/png;base64,{image_data}" alt="Qualification coverage, risk versus resource, governor ablation and blocked-link violation decomposition">
<p>Panel B is a steady-gap case. Panel C uses 20 PRBs per copy, four hopped copies and identical paired
episode streams; error bars are pointwise exact 95% binomial intervals. Log axes show small risks clearly.
These are contract violations, not collision probabilities. Panel D separates disjoint tracking/completion
events; no clearance violations were observed for those governed profiles.</p>
<h2>1. Qualification and comparison</h2>
{table(['Domain','Target h (s)','Selector','PRB-slots','Worst test event fraction'],selection_rows)}
<p>There are 2,048 independent test episodes per profile/population. Reuse across profiles/ablations gives
paired comparisons, not hundreds of thousands of independent deployments. Design/calibration/test have
separate random streams. Test results have now been inspected; any redesign needs fresh final confirmation.</p>
<p>The empirical choice at steady 1.5 s uses 80 PRB-slots and has 43/2,048 correlated-channel violations
(2.100%). Guard uses four times that resource and has 8/2,048 (0.391%). This is a risk/resource trade-off,
not a simultaneous efficiency improvement. Delivery and generous-resource selection choose the identical
Guard action in that case. Bonferroni qualifies no profiles under its prespecified correction.</p>
<p>Guard's 1.5 s test has zero nominal and eight correlated-population violations. Adjusting one-sided
test bounds over those two environments gives upper bounds recorded in <code>analysis.json</code>.
This supports that finite model/population statement; it does not validate shorter maneuvers or road safety.</p>
<h2>2. The governor helps, and its timing cost matters</h2>
{table(['Population','Target h','No governor failures','Governor failures','Governor clearance failures','Governor completion misses','Completion median / 95% (s)'],ablation_rows)}
<p>Completion-time quantiles condition on episodes that finished; misses are shown separately. In LOS
correlated conditions, the 0.6 s request typically finishes around 31 s and the 1.0 s request around 24 s,
despite a nominal six-second reference ramp. The improvement partly comes from slower, gated reconfiguration.
It is not merely a more efficient radio allocation. Fixed-ramp removal is a useful ablation, but it is a
weak comparator for a new controller: published constrained/reference-governor controllers are still needed.</p>
<p>Perfect-radio controls contain 64 episodes per seed batch, while main held-out runs contain 512.
The same seed with different batch sizes does not reproduce every plant draw in this implementation.
Those controls are distribution-matched diagnostics, not episode-paired comparisons with the main runs.</p>
<p>The current admission utility depends on final headway and an illustrative exponential utility,
not the integral of actual headway benefit over the maneuver. The replay does not store that integral.
Completion latency and realized transient benefit must enter the next objective before fuel/utility claims.</p>
<h2>3. Blockage needs a physical/control remedy</h2>
<p>Even the 320-PRB-slot hopped profile has 912/2,048 violations at 0.6 s, 894/2,048 at 1.0 s and
670/2,048 at 1.5 s in the blocked population (44.531%, 43.652%, 32.715%). These are mostly tracking failures,
with many missed completion deadlines in gap-changing cases. Increasing calibration sample size cannot
make those policies satisfy a 1% event-risk target.</p>
<p>A recorded blocked-case witness reaches a 5 m tracking error while a predecessor packet is more than
four seconds old. This is diagnostic evidence of the stale-information regime, not a proof that it is
the sole cause. The radio bank contains only parallel-link templates with 10/20 PRBs per copy;
it omits wider serial-link alternatives that could fit the same total slot bandwidth. An age-aware
local observer/predictive fallback and richer legal scheduling geometry are justified follow-up hypotheses,
with matched baselines and unchanged outcome thresholds.</p>
<h2>4. The allocation demo is structurally too small</h2>
{table(['Domain','Selector','Offered profiles','Minimum first-slot PRBs','Cell PRBs','Admission upper bound'],
       [[x['domain'],x['method'],x['offered_profiles'],x['minimum_first_slot_prbs'],x['cap'],x['first_slot_cardinality_bound']] for x in data['first_slot_bounds']])}
<p>Every offered profile in the LOS comparison occupies 40 of 51 PRBs in its first slot. Consequently
two offered templates cannot coexist under the current common start phase. The exact/greedy agreement at
one admitted tenant does not establish an effective scalable allocator. Guard's sole 1% label independently
also consumes the whole fleet-risk budget. Phase/release choices need explicit qualification or a justified
time-shift invariance argument; shifting packets after calibration without checking their delay/control
effect would invalidate the intended contract.</p>
<h2>5. Short-gap qualification is partly a power issue</h2>
<p>The strongest correlated-channel profiles have 16/2,048 calibration violations for the 0.6 s request,
14/2,048 for 1.0 s and 9/2,048 for steady 1.5 s. At the chain alpha of 0.05/6, the first two do not qualify;
the third does. No later profile would pass an individual 1% test at that same chain level in the
short-gap data, so merely bypassing fixed-sequence stopping does not rescue those cases.</p>
<p>As an analytical sensitivity calculation, if the true risk were 0.65%, qualification power at a 1%
target and alpha 0.05/6 is about 22.5% with 2,048 calibration episodes, 50.3% with 4,096 and 84.1% with 8,192.
These assumed-risk calculations are not new data or new qualifications. Use targeted sample planning
after improving the model/policies; more samples do not fix blocked-case failures or empty scheduling choices.</p>
<h2>6. Compute and next research gate</h2>
<p>All task records identify <code>cn002</code>. Recorded task CPU totals {data['summary']['task_cpu_s']:.3f} s
({data['summary']['task_cpu_s']/3600:.3f} CPU-hours); maximum cumulative process RSS is
{data['summary']['maximum_process_rss_mib']:.3f} MiB. Rank CPU totals range from
{min(r['cpu_s'] for r in data['ranks']):.1f} to {max(r['cpu_s'] for r in data['ranks']):.1f} s.
The pilot demonstrates practical CPU parallelism on one host. Aggregate memory, final Slurm walltime
and multi-node behavior are not established by the exported application summary.</p>
<ol><li>Keep this pilot as exploratory evidence, including rejected cases and non-improvements.</li>
<li>Address stale-information behavior and broaden the feasible schedule/profile bank, with realistic
PHY calibration and application-justified tolerances.</li>
<li>Measure completion cost and actual time-integrated outcome utility; fix the synchronized admission bottleneck.</li>
<li>Evaluate matched published controllers/schedulers and an independent backend, then freeze fresh
calibration/test namespaces for a confirmatory campaign.</li></ol>
<p>{html.escape(data['limitations'])}</p>
<p>Artifacts: <a href="analysis.json">machine-readable analysis</a>, <a href="cells.json">all cell aggregates</a>,
<a href="guard_pilot_findings.svg">vector figure</a>. Source IDs in the JSON trace back to immutable raw records.
The analysis reruns selection/optimization only; it generates no new physical simulation episodes.</p></html>'''
    (output/'report.html').write_text(content)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path,required=True)
    parser.add_argument('--campaign',required=True)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();export=args.export.resolve();output=args.output.resolve();repo=args.repo.resolve()
    if args.campaign!=FROZEN_PILOT:parser.error('This report narrative is pinned to pilot 3098556')
    if output.is_relative_to(export) or export.is_relative_to(output):parser.error('Output must be separate from raw export')
    m,records,summary,verification,base=load_export(export,args.campaign,repo)
    selection=json.loads((base/'selection.json').read_text())
    verification['selection_and_admission_checks']=verify_selection(m,records,selection,repo)
    data=analyze(m,records,summary,verification,selection)
    output.mkdir(parents=True,exist_ok=True)
    (output/'analysis.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    (output/'cells.json').write_text(json.dumps(data['cells'],indent=2,allow_nan=False)+'\n')
    write_figure(data,output);report(data,output)
    print(json.dumps(dict(report=str(output/'report.html'),verified_records=len(records),
                         checked_source_hashes=verification['source_hashes_checked']),indent=2))


if __name__=='__main__':main()
