"""Transparent positive/negative results; separate calibration and held-out value."""
from collections import Counter,defaultdict
import csv
import html
import json
import math
from pathlib import Path
import tarfile
import numpy as np
from contractlab.common import atomic,sha,digest,utc
from contractlab.protocol import cases
from contractlab.allocation import allocate
from contractlab.risk import SCALE,upper_units


def read(path):return json.loads(Path(path).read_text())


def allocation_tasks(config):
    tasks=[]
    for context in config['contexts']:
        for cap in sorted({c['cap'] for c in cases(config)}):
            for load in ([8] if config['preset']=='smoke' else config['loads']):
                for risk in ([.01] if config['preset']=='smoke' else config['deployment_risk_budgets']):
                    for seed in range(config['allocation_repeats']):
                        row=dict(context=context,cap=cap,load=load,budget=round(risk*SCALE),seed=seed)
                        row['id']=sha(row)[:24];tasks.append(row)
    return tasks


def allocation_trial(study,task):
    contracts=read(study/'contracts.json');test=read(study/'test/aggregate.json')
    eligible=[c for c in contracts.values() if c['qualified'] and c['context']==task['context'] and c['case']['cap']==task['cap']]
    available=sorted({c['case']['id'] for c in contracts.values() if c['context']==task['context'] and c['case']['cap']==task['cap']})
    random=np.random.default_rng(task['seed']+5501)
    owners={f'tenant-{i:04d}':str(random.choice(available)) for i in range(task['load'])}
    menus={owner:[c for c in eligible if c['case']['id']==case] for owner,case in owners.items()}
    results={};incumbents=[]
    for name in ['hold','radar','fused','idm','ccc','ccc_cbf','no_radio','static_min_PRB_contract','greedy','contract_union']:
        filtered={o:[c for c in menu if name not in {'hold','radar','fused','idm','ccc','ccc_cbf'} or c['policy']['controller']==name] for o,menu in menus.items()}
        if name=='no_radio':filtered={o:[c for c in menu if c['profile']['copies']==0] for o,menu in filtered.items()}
        if name=='static_min_PRB_contract':
            # Engineering reference, not attributed to a published scheduler.
            from gapslice.certified.profiles import Profile
            filtered={o:sorted(menu,key=lambda c:(Profile(**c['profile']).cost,c['risk_units'],-c['benefit_microseconds'],c['id']))[:1] for o,menu in filtered.items()}
        result=allocate(filtered,task['budget'],task['cap'],method='greedy' if name=='greedy' else 'exact',
                        time_limit=10.,incumbents=incumbents if name=='contract_union' else ())
        allocation=result['allocation'];incumbents.append(allocation)
        result['heldout_expected_successful_gain_s']=sum(test[x['contract']['id']]['reward_sum']/test[x['contract']['id']]['episodes'] for x in allocation)
        result['heldout_empirical_union_bound']=min(1.,sum(test[x['contract']['id']]['failures']/test[x['contract']['id']]['episodes'] for x in allocation))
        # Expected additive value and union bound require no fleet independence.
        # They are not an actually replayed joint fleet risk measurement.
        result['heldout_scope']='Sum of frozen-cell independent-test means and marginal empirical risk union bound; no joint fleet replay'
        results[name]=result
    best=max(x['benefit_microseconds'] for name,x in results.items() if name!='contract_union')
    if results['contract_union']['benefit_microseconds']<best:raise RuntimeError('Baseline-preserving allocator regressed on calibration objective')
    return dict(scenario=task,tenant_cases=owners,methods=results)


def csv_rows(path,rows):
    rows=list(rows)
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',newline='') as stream:
        out=csv.DictWriter(stream,fieldnames=fields);out.writeheader();out.writerows(rows)


def records(study,stage):
    from contractlab.campaign import load
    manifest=read(study/stage/'manifest.json')
    for task in manifest['tasks']:
        row=load(study/stage,task)
        if row is None:raise RuntimeError(f'Missing {stage} result')
        yield row


def paired_contrasts(study,cells):
    """Exact shared-seed/shape contrasts; no fabricated independent replicates."""
    from contractlab.campaign import load
    m=read(study/'test/manifest.json');groups=defaultdict(list);tasks=defaultdict(dict)
    for cid,c in cells.items():groups[(c['case']['id'],c['context'])].append(cid)
    for t in m['tasks']:tasks[t['cell']][t['offset']]=t
    output=[]
    for group,cids in groups.items():
        # Compare every candidate against the matched design-selected no-radio
        # hold control. This retains negative and non-fused comparisons.
        ref=[cid for cid in cids if cells[cid]['policy']['controller']=='hold' and not cells[cid]['profile']['copies']]
        if not ref:continue
        ref=ref[0]
        for cid in sorted(cids):
            if cid==ref:continue
            difference=[]
            for offset,t in sorted(tasks[cid].items()):
                other=tasks[ref][offset]
                if (t['seed'],t['episodes'])!=(other['seed'],other['episodes']):raise RuntimeError('Invalid trajectory pairing')
                a=load(study/'test',t);b=load(study/'test',other)
                with np.load(study/'test/results'/a['raw']) as za,np.load(study/'test/results'/b['raw']) as zb:
                    difference.extend((za['successful_gain_seconds']-zb['successful_gain_seconds']).tolist())
            values=np.array(difference);span=1.5-cells[cid]['profile']['h_target']
            # Simultaneous Hoeffding interval for differences in [-span,span].
            radius=2*span*math.sqrt(math.log(40*len(cells))/(2*len(values)))
            mean=float(values.mean())
            output.append(dict(cell=cid,reference=ref,case=group[0],context=group[1],n=len(values),
                mean_paired_gain_difference_s=mean,simultaneous_lower_s=mean-radius,simultaneous_upper_s=mean+radius,
                conclusion='better' if mean-radius>0 else 'worse' if mean+radius<0 else 'inconclusive',
                pairing_scope='Same initial state/sensor RNG streams and batch shapes; different radio phases need not share the same time-indexed fading path'))
    return output


def report(study):
    study=Path(study);folder=study/'analysis';folder.mkdir(exist_ok=True)
    protocol=read(study/'protocol.json');config=protocol['config'];contracts=read(study/'contracts.json')
    test=read(study/'test/aggregate.json');cells=[];family=len(contracts)
    for cid,c in sorted(contracts.items()):
        r=test[cid];tu=upper_units(r['failures'],r['episodes'],family)
        cells.append(dict(id=cid,controller=c['policy']['controller'],context=c['context'],n_trucks=c['profile']['n_trucks'],
            target=c['profile']['h_target'],cap=c['profile']['cap'],prbs=c['profile']['prbs'],copies=c['profile']['copies'],
            qualified=c['qualified'],calibration_risk_upper=c['risk_upper'],calibration_benefit_lower_s=c['benefit_lower_s'],
            test_n=r['episodes'],test_failures=r['failures'],test_risk=r['failures']/r['episodes'],
            simultaneous_test_risk_upper=tu/SCALE,test_gain_s=r['reward_sum']/r['episodes'],
            test_clearance_failures=r['clearance_failures'],test_tracking_failures=r['tracking_failures'],
            test_completion_failures=r['completion_failures'],maximum_batched_guard_wall_s=r['maximum_batched_guard_wall_s'],
            maximum_observed_l2_acceleration_gain=r['maximum_acceleration_l2_link_gain']))
    csv_rows(folder/'cells.csv',cells)
    contrasts=paired_contrasts(study,contracts);csv_rows(folder/'paired_contrasts.csv',contrasts)
    ext=[x['result'] for x in records(study,'external')];csv_rows(folder/'sumo_validation.csv',ext)
    packet=[x['result'] for x in records(study,'packet')];csv_rows(folder/'packet_baselines.csv',packet)
    allocation=[];wins=Counter();ratios=[];witnesses=0
    method_totals=defaultdict(lambda:dict(instances=0,admitted=0,test_gain=0.,cal_value=0,wall_s=0.,minimum_bound_ratio=1.))
    for record in records(study,'allocation'):
        trial=record['result'];ours=trial['methods']['contract_union']
        for name,r in trial['methods'].items():
            stats=method_totals[name];stats['instances']+=1;stats['admitted']+=r['admitted'];stats['test_gain']+=r['heldout_expected_successful_gain_s'];stats['cal_value']+=r['benefit_microseconds'];stats['wall_s']+=r['wall_s'];stats['minimum_bound_ratio']=min(stats['minimum_bound_ratio'],r['bound_ratio'])
            allocation.append(dict(**trial['scenario'],method=name,admitted=r['admitted'],cal_value_microseconds=r['benefit_microseconds'],
                test_expected_gain_s=r['heldout_expected_successful_gain_s'],test_empirical_risk_union_bound=r['heldout_empirical_union_bound'],
                bound_ratio=r['bound_ratio'],wall_s=r['wall_s'],solver_s=r['solver_s'],solver_status=r['status'],solver_gap=r['solver_gap']))
            if name!='contract_union':
                delta=ours['heldout_expected_successful_gain_s']-r['heldout_expected_successful_gain_s']
                wins[(name,'win' if delta>1e-12 else 'loss' if delta< -1e-12 else 'tie')]+=1
            witnesses+=1
        ratios.append(ours['bound_ratio'])
    csv_rows(folder/'allocation_instances.csv',allocation)
    summaries=[]
    for method,s in method_totals.items():
        n=s['instances'];summaries.append(dict(method=method,instances=n,mean_admitted=s['admitted']/n,
            mean_test_expected_gain_s=s['test_gain']/n,mean_calibration_value_s=s['cal_value']/n/1e6,
            mean_allocator_wall_s=s['wall_s']/n,minimum_bound_ratio=s['minimum_bound_ratio'],
            contract_union_wins=wins[(method,'win')],contract_union_losses=wins[(method,'loss')],contract_union_ties=wins[(method,'tie')]))
    csv_rows(folder/'method_summary.csv',summaries)
    fitted=read(study/'phy_lookup.json')['rows'];heldout=[x['result'] for x in records(study,'phy_holdout')]
    fitmap={(r['prbs'],r['payload'],r['snr_db']):r for r in fitted}
    phy=[]
    for r in heldout:
        f=fitmap[(r['prbs'],r['payload'],r['snr_db'])]
        phy.append(dict(prbs=r['prbs'],payload=r['payload'],snr_db=r['snr_db'],fit_n=f['frames'],fit_bler=f['failures']/f['frames'],
            fit_upper=f['upper'],heldout_n=r['frames'],heldout_bler=r['failures']/r['frames'],
            empirical_exceeds_fit_upper=r['failures']/r['frames']>f['upper']))
    csv_rows(folder/'phy_holdout.csv',phy)
    diagnostics=read(study/'diagnostics/aggregate.json');dm=read(study/'diagnostics/manifest.json')
    csv_rows(folder/'diagnostics.csv',[dict(id=k,kind=dm['cells'][k]['kind'],controller=dm['cells'][k]['policy']['controller'],
        context=dm['cells'][k]['context'],**r) for k,r in diagnostics.items()])
    counts={stage:read(study/stage/'complete.json')['complete'] for stage in
            ['phy_fit','phy_holdout','external','design','calibration','test','diagnostics','packet','allocation']}
    qualified=[x for x in cells if x['qualified']]
    empirical_exceed=sum(x['test_risk']>x['calibration_risk_upper'] for x in qualified)
    simultaneous_inconclusive=sum(x['simultaneous_test_risk_upper']>x['calibration_risk_upper'] for x in qualified)
    summary=dict(study=study.name,preset=config['preset'],completed_tasks=counts,total_tasks=sum(counts.values()),
        calibration_episodes=sum(c['episodes'] for c in read(study/'calibration/aggregate.json').values()),
        heldout_episodes=sum(c['test_n'] for c in cells),contracts=family,qualified=len(qualified),
        empirical_risk_exceedances=empirical_exceed,simultaneous_test_inconclusive=simultaneous_inconclusive,
        checked_allocation_witnesses=witnesses,methods=summaries,paired_contrasts=Counter(x['conclusion'] for x in contrasts),
        sumo_clearance_violation_episodes=sum(x['clearance_violation'] for x in ext),
        phy_heldout_empirical_exceedances=sum(x['empirical_exceeds_fit_upper'] for x in phy),
        readiness=dict(measured_data='UNAVAILABLE',full_NR_Mode1_validation='NOT_IMPLEMENTED',
            nonlinear_string_stability='NOT_PROVEN',external_independent_researcher_replication='NOT_DONE',
            independent_software_backends='EXECUTED: SUMO and py3gpp; bounded scope',
            qualification='RESEARCH_SYNTHETIC' if config['preset']=='research' else 'VERIFICATION_ONLY'),
        limitations='Synthetic distributions and an AWGN-coded lookup. Native versus adapted baselines are separated. Finite-menu calibration dominance is structural, not evidence of held-out superiority. Q1 readiness requires the missing evidence and novelty review.',utc=utc())
    atomic(study/'summary.json',summary)
    def table(rows,fields):
        return '<table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in fields)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(k,'')))+'</td>' for k in fields)+'</tr>' for r in rows)+'</table>'
    page='''<!doctype html><meta charset="utf-8"><title>Contract framework results</title><style>body{font:16px system-ui;max-width:1250px;margin:35px auto;padding:15px;color:#182b3a}table{border-collapse:collapse;width:100%;font-size:13px;margin:20px 0}td,th{border:1px solid #ccd7df;padding:8px;text-align:right}th{background:#edf3f6}p{line-height:1.55}code{background:#edf3f6} .scope{padding:16px;background:#fff4dc}</style>'''
    page+=f'<h1>{study.name}</h1><p class="scope">{html.escape(summary["limitations"])}</p>'
    page+=f'<p>Completed {summary["total_tasks"]:,} required tasks; {len(qualified)}/{family} contracts qualify. {summary["heldout_episodes"]:,} held-out episodes. Empirical risk exceedances: {empirical_exceed}; simultaneous test bounds inconclusive against calibration label: {simultaneous_inconclusive}.</p>'
    page+='<h2>Matched finite-menu allocation</h2><p>Wins and losses compare held-out additive means across the same tenant mix and budgets. They are descriptive, not independent significance tests. Calibration superiority of the union menu is guaranteed by incumbent retention and feasible-set inclusion.</p>'
    page+=table(summaries,list(summaries[0]))
    page+='<h2>Independent software cross-checks</h2><p>SUMO-native IDM, ACC and CACC retain their built-in safety overrides. Custom controls disable hidden speed clamps. SUMO integration has no transferred primary-plant guarantee. Native CACC has ideal cooperative information. These are explicitly different baseline capabilities.</p>'
    groups=defaultdict(list)
    for x in ext:groups[(x['backend'],x['radio'])].append(x)
    page+=table([dict(backend=k[0],radio=k[1],episodes=len(rr),clearance_violations=sum(x['clearance_violation'] for x in rr),physical_target_attainment=sum(x['physical_target_attained'] for x in rr)/len(rr),mean_gain_s=float(np.mean([x['realized_gain_s'] for x in rr]))) for k,rr in groups.items()],['backend','radio','episodes','clearance_violations','physical_target_attainment','mean_gain_s'])
    page+='<p>The NR LDPC backend tests CRC, segmentation, encoding, rate matching, modulation and decoding in AWGN. It does not implement a full NR sidelink stack or measured channel. Per-SNR fitted and held-out block counts are in <a href="analysis/phy_holdout.csv">phy_holdout.csv</a>.</p>'
    page+='<h2>What remains before a strong journal submission</h2>'+table([dict(requirement=k,status=v) for k,v in summary['readiness'].items()],['requirement','status'])
    page+='<p>Review negative diagnostic and paired contrasts before making claims. Acceleration L2 gains are empirical amplification diagnostics, not a string-stability theorem. Actual runtime tails are batch timings, not measured embedded per-vehicle latency. Real data must have provenance and a separate qualification split.</p>'
    page+='<h2>Auditable evidence</h2><ul>'+''.join(f'<li><a href="analysis/{p.name}">{p.name}</a></li>' for p in sorted(folder.glob('*.csv')) )+'</ul><p>All scientific manifests, raw episode vectors and commit hashes remain in the study directory and evidence bundle. The analysis bundle includes every aggregate, allocation witness, protocol and table certificate.</p>'
    (study/'report.html').write_text(page)


def bundle(study):
    study=Path(study)
    metadata=[];evidence=[]
    for p in sorted(study.rglob('*')):
        if not p.is_file() or p.name=='bundle_hashes.json' or p.suffix=='.gz' or 'work' in p.relative_to(study).parts or 'tables' in p.relative_to(study).parts and p.suffix=='.npy':continue
        relative=p.relative_to(study)
        if 'results' in relative.parts:evidence.append(p)
        else:metadata.append(p)
    # Include scalar external/PHY/packet and full allocation witnesses in the
    # compact bundle; numerical raw vectors remain in the evidence bundle.
    compact=[p for p in evidence if p.suffix=='.json' and p.parent.parent.name in {'allocation','external','packet','phy_fit','phy_holdout'}]
    for name,items in [('analysis_bundle.tar.gz',metadata+compact),('evidence_bundle.tar.gz',evidence)]:
        with tarfile.open(study/name,'w:gz') as archive:
            for p in items:archive.add(p,arcname=str(Path(study.name)/p.relative_to(study)))
    atomic(study/'bundle_hashes.json',{p.name:dict(sha256=digest(p),bytes=p.stat().st_size) for p in [study/'analysis_bundle.tar.gz',study/'evidence_bundle.tar.gz']})
