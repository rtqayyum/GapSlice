"""Compile qualified profiles and compare prespecified selection policies.

Design counts rank candidates. Calibration counts qualify them. Test counts
are accessed only after all selections are frozen and have no role in fitting,
ordering, stopping or selecting. Reusing seeds within a split pairs comparisons;
splits use independent hashed random streams.
"""
from dataclasses import asdict
import json
import math

import numpy as np
from scipy.stats import binom

from gapslice.guard.profiles import Profile, admit
from gapslice.guard.risk import certify, upper_bound


def contract_key(profile):
    names=['n_trucks','h_initial','h_target','ramp_s','payload_bytes','cap']
    return json.dumps({k:asdict(profile)[k] for k in names},sort_keys=True,separators=(',',':'))


def compile_catalog(profiles, records, delta=.01, alpha=.05):
    by_key={p.key:p for p in profiles}
    if not profiles or len(by_key)!=len(profiles):
        raise ValueError('Require unique, nonempty profiles')
    if len({r['id'] for r in records})!=len(records):
        raise ValueError('Duplicated evidence records cannot increase the sample count')
    groups={}
    domains=sorted({r['config']['environment'] for r in records})
    # Read only design/calibration metrics while building selectors.
    counts={split:{key:{env:dict(failures=0,episodes=0,packet_failures=0,packet_trials=0)
            for env in domains} for key in by_key} for split in ['design','calibration']}
    for r in records:
        c=r['config']
        if c['split'] not in counts:
            continue
        v=r['metrics'];cell=counts[c['split']][c['profile_id']][c['environment']]
        cell['failures']+=v['failures'];cell['episodes']+=v['episodes']
        cell['packet_failures']+=v['packet_failures']
        cell['packet_trials']+=v['episodes']*v['packet_trials_per_episode']
    for p in profiles:
        p.check()
        groups.setdefault(contract_key(p),[]).append(p.key)
    for split in counts:
        if any(c['episodes']==0 for key in counts[split] for c in counts[split][key].values()):
            raise ValueError('Every profile/environment needs design and calibration episodes')
    decisions=[]
    all_accepted={name:{} for name in ['guard','bonferroni','empirical_outcome','delivery_proxy','max_reservation']}
    for group, keys in sorted(groups.items()):
        def design_risk(key):
            return max(v['failures']/v['episodes'] for v in counts['design'][key].values())
        def packet_risk(key):
            return max(v['packet_failures']/v['packet_trials'] for v in counts['design'][key].values())
        risk_levels=[delta/4,delta/2,delta]
        hypotheses={f'{key}@{target:.8g}':(key,target) for key in keys for target in risk_levels}
        def design_priority(label):
            key,target=hypotheses[label]
            anticipated=max(float(binom.cdf(math.ceil(counts['design'][key][env]['failures']/
                counts['design'][key][env]['episodes']*counts['calibration'][key][env]['episodes']),
                counts['calibration'][key][env]['episodes'],target)) for env in domains)
            return anticipated,design_risk(key)/target,packet_risk(key),-by_key[key].cost,label
        # Ordering uses design losses and predetermined calibration sample
        # sizes, never calibration failure counts.
        order=sorted(hypotheses,key=design_priority)
        cal={label:{env:{field:c[field] for field in ['failures','episodes']}
                   for env,c in counts['calibration'][key].items()} for label,(key,_) in hypotheses.items()}
        targets={label:target for label,(_,target) in hypotheses.items()}
        chain_alpha=alpha/len(groups)
        guard=certify(order,cal,delta,chain_alpha,'fixed_sequence',targets)
        bonf=certify(order,cal,delta,chain_alpha,'bonferroni',targets)
        def risk_frontier(qualified):
            frontier={}
            for label in qualified:
                key,target=hypotheses[label]
                frontier[key]=min(frontier.get(key,1.),target)
            return frontier
        empirical=[key for key in keys if design_risk(key)<=delta]
        # A clearly named heuristic proxy, not a reproduction of the original
        # interpolation-based method. Same robust environment set and schedules.
        delivery=[key for key in keys if packet_risk(key)<=.01]
        strongest=[min(keys,key=lambda key:(-by_key[key].cost,packet_risk(key),key))]
        qualified=dict(guard=risk_frontier(guard['accepted']),bonferroni=risk_frontier(bonf['accepted']),
                       empirical_outcome={k:design_risk(k) for k in empirical},
                       delivery_proxy={k:design_risk(k) for k in delivery},max_reservation={k:design_risk(k) for k in strongest})
        selected={}
        for method, accepted in qualified.items():
            all_accepted[method].update(accepted)
            selected[method]=(min(accepted,key=lambda key:(by_key[key].cost,design_risk(key),key))
                              if accepted else None)
        decisions.append(dict(contract=json.loads(group),guard=guard,bonferroni=bonf,
            design_order=order,risk_frontiers=qualified,design_summary={key:dict(risk=design_risk(key),packet_loss=packet_risk(key),
                prb_slots=by_key[key].cost) for key in keys},selected=selected))
    # Test evidence is deliberately read only after every method's selection.
    test={key:{env:[] for env in domains} for key in by_key}
    for r in records:
        c=r['config']
        if c['split']=='test':
            test[c['profile_id']][c['environment']].append(r)
    for decision in decisions:
        evaluation={}
        for method,key in decision['selected'].items():
            if key is None:
                evaluation[method]=dict(selected=None,abstained=True)
                continue
            envs={}
            for env,rs in test[key].items():
                n=sum(r['metrics']['episodes'] for r in rs)
                k=sum(r['metrics']['failures'] for r in rs)
                if n==0:
                    raise ValueError('Every selected profile needs held-out test episodes')
                envs[env]=dict(failures=k,episodes=n,event_fraction=k/n,
                    pointwise_one_sided_test_95_upper=upper_bound(k,n,.05),
                    mean_peak_error_m=float(np.mean([v for r in rs for v in r['metrics']['peak_error_m']])),
                    clearance_failures=sum(r['metrics']['clearance_failures'] for r in rs),
                    source_ids=[r['id'] for r in rs])
            evaluation[method]=dict(selected=key,abstained=False,prb_slots=by_key[key].cost,
                                    declared_risk=decision['risk_frontiers'][method][key],
                                    statistically_qualified=method in {'guard','bonferroni'},
                                    profile=asdict(by_key[key]),test_environments=envs)
        decision['evaluation']=evaluation
    # Small transparent admission comparison; not a new optimization algorithm.
    admission={}
    homogeneous=(len({(p.n_trucks,p.cap,p.h_initial,p.ramp_s,p.payload_bytes) for p in profiles})==1)
    if homogeneous:
        for method,accepted in all_accepted.items():
            menus={f'tenant-{i}':[(by_key[key],float(weight*(np.exp(-by_key[key].h_target/.8)-np.exp(-2.8/.8))))
                    for key in accepted] for i,weight in enumerate([.7,.9,1.1,1.3])}
            admission[method]=dict(greedy=admit(menus,'greedy',risk_budget=delta,risk_costs=accepted),
                                  exact=admit(menus,'exact',risk_budget=delta,risk_costs=accepted),
                                  risk_costs_are_qualified=method in {'guard','bonferroni'})
    return dict(method='GapSlice-Guard research prototype',delta_episode=delta,alpha_family=alpha,
        contract_chains=len(groups),risk_levels=[delta/4,delta/2,delta],fleet_risk_budget=delta,
        environments=domains,profiles={k:asdict(p) for k,p in by_key.items()},
        decisions=decisions,admission=admission,
        qualification='Fixed-sequence exact binomial tests with pre-calibration design ordering. '
            'Existing statistical machinery, not claimed as a new theorem.',
        limitations='Finite synthetic iid episode populations only. Within-episode link/packet dependence '
            'is retained. No claim under distribution shift or arbitrary initial states. '
            'Frequency translations require stationary channel law and no extra in-cell interference. '
            'Abstention rejects a requested maneuver; it is not an instantaneous safe ACC transition.')
