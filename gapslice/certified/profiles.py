"""Cyclic, half-duplex-safe reservations with qualified absolute packet phases.

The 100 ms superframe has three releases (0, 40, 70 ms) plus a declared
10 ms phase offset. This is an explicit quantized 30 Hz source, not continuous
periodic traffic silently rounded differently by the scheduler and simulator.
"""
from dataclasses import asdict,dataclass
import hashlib
import json
import math
import warnings

import numpy as np
from scipy.optimize import Bounds,LinearConstraint,milp
from scipy.sparse import lil_matrix

from gapslice.guard.phy import transport
from gapslice.revision.slot_schedule import Job,Placement,validate


SUPERFRAME_SLOTS=200
RELEASE_SLOTS=(0,80,140)


@dataclass(frozen=True)
class Profile:
    n_trucks:int=5
    h_initial:float=1.5
    h_target:float=1.
    ramp_s:float=6.
    prbs:int=20
    copies:int=4
    pattern:str='hopped'
    layout:str='parallel'
    phase:int=0
    payload_bytes:int=300
    cap:int=51
    deadline_slots:int=18
    slot_s:float=.0005

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]

    @property
    def cost(self):return 3*(self.n_trucks-1)*self.copies*self.prbs

    def relative(self):
        if self.layout=='none' and self.copies==0 and self.prbs==0 and self.pattern=='none' and self.phase==0:
            return []
        if (self.layout not in {'parallel','serial'} or self.pattern not in {'clustered','spread','hopped'}
                or self.copies not in {1,2,4} or not 0<=self.phase<10 or self.n_trucks<2):
            raise ValueError('Invalid profile geometry')
        links=self.n_trucks-1;round_slots=2 if self.layout=='parallel' else links
        if round_slots*self.copies>self.deadline_slots:raise ValueError('Copies do not fit radio deadline')
        bases=([j*round_slots for j in range(self.copies)] if self.pattern=='clustered' else
               [0] if self.copies==1 else
               [round(j*(self.deadline_slots-round_slots)/(self.copies-1)) for j in range(self.copies)])
        width=math.ceil(links/2)*self.prbs if self.layout=='parallel' else self.prbs
        result=[]
        for copy,base in enumerate(bases):
            for link in range(links):
                slot=base+(link%2 if self.layout=='parallel' else link)
                rb=(link//2)*self.prbs if self.layout=='parallel' else 0
                if self.pattern=='hopped' and copy%2:
                    rb=width-self.prbs-rb if self.layout=='parallel' else max(0,(self.cap-self.prbs)//10*10)
                result.append((link,copy,slot,rb))
        return result

    @property
    def width(self):return max((rb+self.prbs for _,_,_,rb in self.relative()),default=0)

    def placements(self,tenant='p',offset=0,epochs=(0,)):
        result=[]
        for epoch in epochs:
            for number,release in enumerate(RELEASE_SLOTS):
                release+=self.phase*20+epoch*SUPERFRAME_SLOTS
                for link,copy,slot,rb in self.relative():
                    packet=f'{tenant}/{epoch}/{number}/{link}'
                    job=Job(f'{packet}/{copy}',packet,f'{tenant}/v{link}',f'{tenant}/v{link+1}',
                            self.prbs,release,release+self.deadline_slots)
                    result.append(Placement(job,release+slot,offset+rb))
        return result

    def cells(self,offset=0):
        return {(p.slot%SUPERFRAME_SLOTS,rb) for p in self.placements(offset=offset)
                for rb in range(p.first_prb,p.first_prb+p.job.prbs)}

    def check(self):
        if (self.slot_s!=.0005 or self.deadline_slots>18 or min(self.h_initial,self.h_target,self.ramp_s)<=0
                or self.h_target>self.h_initial):
            raise ValueError('Unsupported timing or maneuver')
        pp=self.placements(epochs=(-1,0,1));errors=validate(pp,self.cap,[p.job for p in pp])
        if self.copies and (self.prbs%10 or transport(self.prbs,self.payload_bytes) is None):errors.append('Payload/subchannel infeasible')
        if len(self.cells())!=self.cost:errors.append('Cyclic self-overlap')
        if errors:raise ValueError('; '.join(errors))
        return dict(profile_id=self.key,checked_jobs=len(pp),prb_slots_per_100ms=self.cost,
                    certificate='Three-epoch independent overlap/half-duplex/deadline checker')

    def release_ticks(self):return {(self.phase+x)%10 for x in [0,4,7]}


def catalog(n=5,h=1.,cap=51,payload=300,phases=(0,2,4,6,8),broad=False):
    result=[Profile(n_trucks=n,h_target=h,prbs=0,copies=0,pattern='none',layout='none',payload_bytes=payload,cap=cap)];seen=set()
    for layout in ['parallel','serial']:
        for b in ([10,20,30,40,50,60,80,100] if broad else [10,20,40]):
            for copies in [1,2,4]:
                for pattern in ['clustered','spread','hopped']:
                    for phase in phases:
                        p=Profile(n_trucks=n,h_target=h,prbs=b,copies=copies,pattern=pattern,
                                  layout=layout,phase=phase,cap=cap,payload_bytes=payload)
                        try:p.check()
                        except ValueError:continue
                        geometry=p.prbs,tuple((link,copy,slot,rb) for link,copy,slot,rb in p.relative()),phase
                        if geometry not in seen:seen.add(geometry);result.append(p)
    return result


def allocate(menus,risk_costs,risk_budget=16,method='greedy',time_limit=60.):
    """Finite-catalog packing with integer risk units and benefit microseconds.

    The independent multiple-choice knapsack DP ignores radio conflicts and
    bounds every feasible packing from above. Its bound is exact integer
    arithmetic, independent of the floating MILP solver's optimality claim.
    """
    if type(risk_budget) is not int or risk_budget<=0:raise ValueError('Integer risk budget required')
    dp=[0]*(risk_budget+1)
    for tenant,menu in sorted(menus.items()):
        previous=dp.copy()
        for p,benefit in menu:
            risk=risk_costs[p.key]
            if type(benefit) is not int or benefit<0 or type(risk) is not int or risk<=0:
                raise ValueError('Integer nonnegative benefit and positive risk units required')
            for budget in range(risk,risk_budget+1):
                dp[budget]=max(dp[budget],previous[budget-risk]+benefit)
    independent_upper=dp[-1]
    cap=next((p.cap for menu in menus.values() for p,_ in menu),51)
    columns=[]
    for tenant,menu in sorted(menus.items()):
        for p,benefit in menu:
            p.check();risk=risk_costs[p.key]
            if p.cap!=cap or not 0<risk<=risk_budget:raise ValueError('Inconsistent allocation input')
            if benefit<=0:continue
            for offset in ((0,) if p.copies==0 else range(0,cap-p.width+1,10)):
                columns.append((tenant,p,benefit,offset,p.cells(offset),risk))
    chosen=[];status='heuristic';gap=None;bound=None
    if method=='greedy':
        cells=set();owners=set();spent=0
        def value(c):return c[2]/(len(c[4])/(SUPERFRAME_SLOTS*cap)+c[5]/risk_budget+1e-15)
        for c in sorted(columns,key=lambda c:(-value(c),-c[2],c[0],c[1].key,c[3])):
            if c[0] not in owners and not cells.intersection(c[4]) and spent+c[5]<=risk_budget:
                chosen.append(c);owners.add(c[0]);cells.update(c[4]);spent+=c[5]
    elif method=='exact' and columns:
        owners=sorted(menus);owner_index={x:i for i,x in enumerate(owners)}
        cells=sorted(set.union(*(c[4] for c in columns)));cell_index={c:i for i,c in enumerate(cells)}
        matrix=lil_matrix((len(owners)+len(cells)+1,len(columns)))
        for j,c in enumerate(columns):
            matrix[owner_index[c[0]],j]=1
            for cell in c[4]:matrix[len(owners)+cell_index[cell],j]=1
            matrix[-1,j]=c[5]/risk_budget
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore',message='Unrecognized options detected.*')
            res=milp(-np.array([c[2] for c in columns]),integrality=np.ones(len(columns)),bounds=Bounds(0,1),
                constraints=LinearConstraint(matrix.tocsr(),0,1),
                options={'threads':1,'time_limit':time_limit,'mip_rel_gap':0.})
        if res.x is None:raise RuntimeError('No admission incumbent: '+res.message)
        chosen=[c for c,x in zip(columns,res.x) if x>.5]
        status='optimal' if res.status==0 else f'incumbent_{res.status}'
        gap=float(res.mip_gap);bound=float(-res.mip_dual_bound)
    elif method=='exact':status='optimal';gap=0.;bound=0.
    else:raise ValueError('Unknown allocator')
    if len({c[0] for c in chosen})!=len(chosen):raise AssertionError('Multiple choices for one tenant')
    pp=[x for tenant,p,_,offset,_,_ in chosen for x in p.placements(tenant,offset,(-1,0,1))]
    if validate(pp,cap,[x.job for x in pp]):raise AssertionError('Global cyclic checker rejected allocation')
    spent=sum(c[5] for c in chosen)
    if spent>risk_budget:raise AssertionError('Fleet risk budget exceeded')
    value=sum(c[2] for c in chosen)
    if value>independent_upper:raise AssertionError('Independent integer upper bound violated')
    return dict(status=status,relative_gap=gap,solver_objective_upper_bound=bound,
        independent_integer_upper_bound=independent_upper,independently_optimal=value==independent_upper,
        guaranteed_catalog_ratio=1. if independent_upper==0 else value/independent_upper,
        benefit_microseconds=value,
        admitted=len(chosen),risk_spent=spent,risk_budget=risk_budget,
        prb_slots_per_100ms=sum(c[1].cost for c in chosen),checked_jobs=len(pp),
        allocation=[dict(tenant=c[0],profile=c[1].key,frequency_offset=c[3],risk_label=c[5]) for c in chosen])
