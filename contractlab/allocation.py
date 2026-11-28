"""Finite contract packing, independently checked witnesses and integer bounds."""
from fractions import Fraction
import math
import time
import warnings
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix
from gapslice.certified.profiles import Profile
from gapslice.revision.slot_schedule import validate


def upper_bound(menus,budget):
    # Lagrangian relaxation discards radio conflicts; each rational value is a
    # valid upper bound. Integer ceil preserves validity without solver floats.
    slopes={Fraction(0)}
    for menu in menus.values():
        for c in menu:
            if c['risk_units']>0:slopes.add(Fraction(c['benefit_microseconds'],c['risk_units']))
    best=None
    for slope in slopes:
        value=slope*budget+sum(max([Fraction(0)]+[
            Fraction(c['benefit_microseconds'])-slope*c['risk_units'] for c in menu]) for menu in menus.values())
        rounded=math.ceil(value)
        best=rounded if best is None else min(best,rounded)
    return best or 0


def check(chosen, budget, cap):
    owners=set();cells=set();spent=0;benefit=0;placements=[]
    for row in chosen:
        p=Profile(**row['contract']['profile']);p.check()
        if p.cap!=cap or row['tenant'] in owners:raise RuntimeError('Mixed cap/duplicate tenant')
        offset=row['offset'];cc=p.cells(offset)
        if cells & cc:raise RuntimeError('Radio conflict')
        if row['contract']['risk_units']<=0:raise RuntimeError('Nonpositive risk cost')
        owners.add(row['tenant']);cells|=cc;spent+=row['contract']['risk_units']
        benefit+=row['contract']['benefit_microseconds']
        placements.extend(p.placements(row['tenant'],offset,(-1,0,1)))
    errors=validate(placements,cap,[p.job for p in placements])
    if spent>budget or errors:raise RuntimeError(f'Invalid witness: {errors}, risk={spent}/{budget}')
    return dict(admitted=len(chosen),risk_spent=spent,benefit_microseconds=benefit,
                prb_slots=len(cells),checked_jobs=len(placements))


def allocate(menus,budget,cap,method='exact',time_limit=20.,incumbents=()):
    start=time.perf_counter();columns=[]
    for owner,menu in sorted(menus.items()):
        for c in menu:
            if c['benefit_microseconds']<=0 or not 0<c['risk_units']<=budget:continue
            p=Profile(**c['profile']);p.check()
            for offset in ((0,) if not p.copies else range(0,cap-p.width+1,10)):
                columns.append(dict(tenant=owner,contract=c,offset=offset,cells=p.cells(offset)))
    def greedy():
        chosen=[];owners=set();cells=set();spent=0
        def merit(x):return x['contract']['benefit_microseconds']/(x['contract']['risk_units']/budget+len(x['cells'])/(200*cap)+1e-12)
        for row in sorted(columns,key=lambda x:(-merit(x),x['tenant'],x['contract']['id'],x['offset'])):
            if row['tenant'] in owners or row['cells']&cells or spent+row['contract']['risk_units']>budget:continue
            chosen.append(row);owners.add(row['tenant']);cells|=row['cells'];spent+=row['contract']['risk_units']
        return chosen
    chosen=greedy();status='greedy';solver_s=0.;solver_gap=None
    # Only incumbents that are legal members of this exact menu can be kept.
    allowed={(x['tenant'],x['contract']['id'],x['offset']) for x in columns}
    for candidate in incumbents:
        if all((x['tenant'],x['contract']['id'],x['offset']) in allowed for x in candidate):
            if check(candidate,budget,cap)['benefit_microseconds']>check(chosen,budget,cap)['benefit_microseconds']:chosen=candidate
    if method=='exact' and columns:
        owners=sorted(menus);oi={x:i for i,x in enumerate(owners)}
        cells=sorted(set().union(*(x['cells'] for x in columns)));ci={x:i for i,x in enumerate(cells)}
        matrix=lil_matrix((len(owners)+len(cells)+1,len(columns)))
        for j,x in enumerate(columns):
            matrix[oi[x['tenant']],j]=1
            for cell in x['cells']:matrix[len(owners)+ci[cell],j]=1
            matrix[-1,j]=x['contract']['risk_units']/budget
        before=time.perf_counter()
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore',message='Unrecognized options detected.*')
            result=milp(-np.array([x['contract']['benefit_microseconds'] for x in columns],dtype=float)/1e6,
                integrality=np.ones(len(columns)),bounds=Bounds(0,1),
                constraints=LinearConstraint(matrix.tocsr(),0,1),
                options={'threads':1,'time_limit':time_limit,'mip_rel_gap':0.})
        solver_s=time.perf_counter()-before;status=f'solver_{result.status}'
        if result.x is not None:
            candidate=[x for x,v in zip(columns,result.x) if v>.5]
            a=check(candidate,budget,cap);b=check(chosen,budget,cap)
            if a['benefit_microseconds']>=b['benefit_microseconds']:chosen=candidate
            solver_gap=float(result.mip_gap)
    elif method not in {'exact','greedy'}:raise ValueError('Unknown method')
    chosen=[{k:v for k,v in x.items() if k!='cells'} for x in chosen]
    metrics=check(chosen,budget,cap);upper=upper_bound(menus,budget)
    if metrics['benefit_microseconds']>upper:raise RuntimeError('Independent upper bound contradicted')
    return dict(**metrics,status=status,allocation=chosen,integer_upper_bound=upper,
                bound_ratio=metrics['benefit_microseconds']/upper if upper else 1.,
                solver_gap=solver_gap,solver_s=solver_s,wall_s=time.perf_counter()-start,
                columns=len(columns),risk_budget=budget)
