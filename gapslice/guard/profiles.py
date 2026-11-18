"""Executable periodic packet-copy templates and resource-cell admission.

No in-cell spatial reuse; nonadjacent platoon links can transmit in parallel
on disjoint PRBs. Every published profile passes the independent slot checker.
The compiler may translate a template in frequency, preserving its time/frequency
separations. Stationary frequency statistics are required for certificate reuse.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import warnings

from gapslice.guard.phy import transport
from gapslice.revision.slot_schedule import Job, Placement, validate


@dataclass(frozen=True)
class Profile:
    n_trucks: int
    h_initial: float
    h_target: float
    ramp_s: float
    prbs: int
    copies: int
    pattern: str
    payload_bytes: int=300
    cap: int=51
    deadline_slots: int=18  # 9 ms radio + 1 ms processing within a 10 ms deadline
    slot_s: float=.0005
    governor: bool=True

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]

    def placements(self, tenant='p', offset=0):
        if (self.n_trucks < 2 or self.copies not in {1,2,4} or self.pattern not in {'clustered','spread','hopped'}
                or min(self.h_initial,self.h_target,self.ramp_s) <= 0 or self.deadline_slots < 2*self.copies):
            raise ValueError('Unsupported profile geometry or gap maneuver')
        width=math.ceil((self.n_trucks-1)/2)
        bases=([2*j for j in range(self.copies)] if self.pattern == 'clustered' else
               [0] if self.copies == 1 else
               [round(j*(self.deadline_slots-2)/(self.copies-1)) for j in range(self.copies)])
        result=[]
        for j, base in enumerate(bases):
            for link in range(self.n_trucks-1):
                channel=link//2
                if self.pattern == 'hopped' and j%2:
                    channel=width-1-channel if width > 1 else 1
                job=Job(f'{tenant}/{link}/{j}', f'{tenant}/{link}', f'{tenant}/v{link}',
                        f'{tenant}/v{link+1}',self.prbs,0,self.deadline_slots)
                result.append(Placement(job,base+link%2,offset+channel*self.prbs))
        return result

    @property
    def cost(self):
        return (self.n_trucks-1)*self.copies*self.prbs

    @property
    def width(self):
        return max(p.first_prb+p.job.prbs for p in self.placements())

    def check(self):
        placements=self.placements()
        errors=validate(placements,self.cap,[p.job for p in placements])
        if transport(self.prbs,self.payload_bytes) is None:
            errors.append('payload does not fit any configured MCS')
        if errors:
            raise ValueError('; '.join(errors))
        return dict(profile_id=self.key,jobs=len(placements),prb_slots=self.cost,
                    width=self.width,deadline_s=self.deadline_slots*self.slot_s+.001,
                    constraints='nonoverlap, conservative half-duplex, distinct copy slots, radio deadline, payload fit')

    def cells(self, offset=0):
        return {(p.slot,rb) for p in self.placements(offset=offset)
                for rb in range(p.first_prb,p.first_prb+p.job.prbs)}


def catalog(n_trucks=5, h_target=1., cap=51, extensive=False, include_unguarded=False):
    result, seen=[],set()
    for b in ([10,20,30,40,50] if extensive else [10,20]):
        for copies in [1,2,4]:
            for pattern in ['clustered','spread','hopped']:
                p=Profile(n_trucks,1.5,h_target,6.,b,copies,pattern,cap=cap)
                try:
                    p.check()
                except ValueError:
                    continue
                geometry=tuple(sorted((place.job.packet,place.slot,place.first_prb,place.job.prbs)
                                      for place in p.placements()))
                if geometry not in seen:
                    seen.add(geometry);result.append(p)
                    if include_unguarded:
                        result.append(Profile(**{**asdict(p),'governor':False}))
    return result


def admit(menus, method='greedy', time_limit_s=30, risk_budget=None, risk_costs=None):
    """Choose at most one qualified profile per tenant; never infer qualification.

    menus[tenant] = [(Profile, utility_above_outside_option), ...].
    Empty/rejected tenants remain unadmitted: no instantaneous ACC-safe claim.
    Exact MILP is a full-information finite-catalog reference, not a new solver.
    Every returned global schedule is independently checked.
    """
    columns=[]
    caps={p.cap for menu in menus.values() for p,_ in menu}
    if len(caps)>1:
        raise ValueError('All profiles must share one cell bandwidth')
    if risk_budget is not None and (not 0 < risk_budget < 1 or risk_costs is None):
        raise ValueError('A positive fleet risk budget requires declared profile risk costs')
    cap=next(iter(caps),51)
    for tenant,menu in sorted(menus.items()):
        for p,value in menu:
            p.check()
            if not math.isfinite(value) or value <= 0:
                continue
            risk=0. if risk_budget is None else risk_costs[p.key]
            if not math.isfinite(risk) or not 0 <= risk <= 1:
                raise ValueError('Invalid profile risk cost')
            for offset in range(0,cap-p.width+1,10):
                columns.append((tenant,p,float(value),offset,p.cells(offset),risk))
    chosen=[];status='heuristic';gap=None
    if method == 'greedy':
        occupied=set();owners=set();risk_used=0.
        def score(c):
            return c[2]/(len(c[4])/(cap*c[1].deadline_slots)+(c[5]/risk_budget if risk_budget else 0.))
        for col in sorted(columns,key=lambda c:(-score(c),-c[2],c[0],c[1].key,c[3])):
            if (col[0] not in owners and not occupied.intersection(col[4]) and
                    (risk_budget is None or risk_used+col[5]<=risk_budget+1e-12)):
                chosen.append(col);owners.add(col[0]);occupied.update(col[4])
                risk_used+=col[5]
    elif method == 'exact' and columns:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import lil_matrix
        owners=sorted(menus)
        cells=sorted(set.union(*(c[4] for c in columns)))
        indices={c:i for i,c in enumerate(cells)}
        a=lil_matrix((len(owners)+len(cells)+int(risk_budget is not None),len(columns)))
        owner_index={o:i for i,o in enumerate(owners)}
        for j,c in enumerate(columns):
            a[owner_index[c[0]],j]=1
            for cell in c[4]:
                a[len(owners)+indices[cell],j]=1
            if risk_budget is not None:a[-1,j]=c[5]/risk_budget
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore',message='Unrecognized options detected.*')
            result=milp(-np.array([c[2] for c in columns]),integrality=np.ones(len(columns)),
                bounds=Bounds(0,1),constraints=LinearConstraint(a.tocsr(),0,1),
                options={'time_limit':time_limit_s,'mip_rel_gap':0.,'threads':1})
        if result.x is None:
            raise RuntimeError(f'Admission MILP returned no incumbent: {result.message}')
        chosen=[c for c,x in zip(columns,result.x) if x > .5]
        status='optimal' if result.status==0 else f'incumbent_status_{result.status}'
        gap=None if getattr(result,'mip_gap',None) is None else float(result.mip_gap)
    elif method != 'exact':
        raise ValueError('Unknown admission method')
    elif not columns:
        status='optimal';gap=0.
    placements=[place for tenant,p,_,offset,_,_ in chosen for place in p.placements(tenant,offset)]
    errors=validate(placements,cap,[place.job for place in placements])
    if errors:
        raise AssertionError(errors)
    risk_used=math.fsum(c[5] for c in chosen)
    if risk_budget is not None and risk_used>risk_budget+1e-12:
        raise AssertionError('Fleet risk budget exceeded')
    return dict(status=status,relative_gap=gap,utility=sum(c[2] for c in chosen),
        admitted=len(chosen),total_prb_slots=sum(c[1].cost for c in chosen),
        allocation=[dict(tenant=c[0],profile=c[1].key,frequency_offset=c[3],risk_cost=c[5]) for c in chosen],
        declared_risk_spent=risk_used,fleet_risk_budget=risk_budget,
        checked_jobs=len(placements),rejected=sorted(set(menus)-{c[0] for c in chosen}))
