"""Outward-rounded backup envelopes for a sampled actuator with bounded lag.

The certificate compares an upper ego displacement with a lower predecessor
displacement, including the intervals between envelope samples and the terminal
stopping tail. No packet-delivery assumption enters this calculation.
See CERTIFIED_PROOFS.md for the inequalities and stored-backup induction.
"""
from dataclasses import asdict,dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np


def up(x):return np.nextafter(x,np.inf)
def down(x):return np.nextafter(x,-np.inf)


def exp_integral_bounds(h,eta,terms=12):
    """Enclose exp(-h/eta) and its integral with bounded Taylor remainders.

    No libm exponential accuracy assumption is used. Operations round outwards;
    h/eta <= 1 ensures decreasing alternating terms. Input constants are the
    exact values represented by their binary64 encodings.
    """
    if not 0<h<=eta or terms<4:raise ValueError('Require 0 < h <= eta and enough Taylor terms')
    xl=float(down(h/eta));xh=float(up(h/eta));result=[]
    for integral in [False,True]:
        lo=hi=tl=th=1.
        for k in range(1,terms+1):
            divisor=k+1 if integral else k
            tl=float(down(down(tl*xl)/divisor));th=float(up(up(th*xh)/divisor))
            if k%2:lo=float(down(lo-th));hi=float(up(hi-tl))
            else:lo=float(down(lo+tl));hi=float(up(hi+th))
        next_term=float(up(up(th*xh)/(terms+2 if integral else terms+1)))
        lo=float(down(lo-next_term));hi=float(up(hi+next_term))
        if integral:lo=float(down(h*lo));hi=float(up(h*hi))
        result.append((lo,hi))
    return result[0],result[1]


@dataclass(frozen=True)
class Bounds:
    eta_min:float=.25
    eta_max:float=.45
    brake:float=6.
    acceleration_max:float=2.
    command_jerk:float=8.
    actual_jerk_bound:float=9.
    control_s:float=.01
    guard_s:float=.04
    envelope_s:float=.02
    horizon_s:float=12.
    terminal_brake:float=5.
    maximum_speed:float=40.
    acceleration_grid:float=.10
    command_grid:float=.10
    range_error_m:float=.10
    own_speed_error_mps:float=.01
    relative_speed_error_mps:float=.04
    own_acceleration_error_mps2:float=.02
    minimum_clearance_m:float=2.

    def check(self):
        if any(not math.isfinite(x) or x<=0 for x in asdict(self).values()):raise ValueError('Positive finite bounds required')
        if not 0<self.envelope_s<=self.eta_min<=self.eta_max:raise ValueError('Invalid lag/envelope range')
        if not 0<self.terminal_brake<self.brake or self.command_jerk<=0:raise ValueError('Invalid braking bounds')
        for a,b in [(self.envelope_s,self.control_s),(self.horizon_s,self.envelope_s),
                    (self.guard_s,self.envelope_s),
                    (self.brake+self.acceleration_max,self.acceleration_grid),
                    (self.brake+self.acceleration_max,self.command_grid)]:
            if not math.isclose(a/b,round(a/b),abs_tol=1e-10):raise ValueError('Incommensurate proof grid')
        c,_=exp_integral_bounds(self.control_s,self.eta_min)
        jerk_hi=float(up(up(self.command_jerk*self.control_s)/down(self.eta_min*down(1-c[1]))))
        if jerk_hi>self.actual_jerk_bound:raise ValueError('Declared actual-jerk bound is too small')
        return jerk_hi

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]


def axes(b):
    return (np.linspace(-b.brake,b.acceleration_max,round((b.brake+b.acceleration_max)/b.acceleration_grid)+1),
            np.linspace(-b.brake,b.acceleration_max,round((b.brake+b.acceleration_max)/b.command_grid)+1))


def ego_envelope(v,a,u,b,prefix):
    """Upper displacement curves; last entry also bounds the infinite tail."""
    v,a,u=np.broadcast_arrays(v,a,u)
    v=v.astype(float).copy();a=a.astype(float).copy();u=u.astype(float).copy()
    h=b.envelope_s;steps=round(b.horizon_s/h);q=np.zeros_like(v)
    c5lo=exp_integral_bounds(h,b.eta_min)[0][0];c5hi=exp_integral_bounds(h,b.eta_max)[0][1]
    c3lo=exp_integral_bounds(h,b.eta_min)[1][0];c3hi=exp_integral_bounds(h,b.eta_max)[1][1]
    yield q.copy()
    for k in range(steps):
        in_prefix=prefix and k<round(b.guard_s/h)
        if in_prefix:u=np.minimum(b.acceleration_max,up(u+up(b.command_jerk*h)))
        positive=np.maximum(np.maximum(a,u),0.)
        displacement=up(up(h*v)+up(up(.5*h*h)*positive))
        q=up(q+displacement)
        difference=up(a-u)
        dv=up(up(h*u)+up(np.where(difference>=0,c3hi,c3lo)*difference))
        # The positive-acceleration branch covers a stop/restart within a step.
        v=np.maximum(np.maximum(0.,up(v+dv)),up(h*positive))
        a=up(u+up(np.where(difference>=0,c5hi,c5lo)*difference))
        if not in_prefix:u=np.maximum(-b.brake,up(u-down(b.command_jerk*h)))
        yield q.copy()
    if np.any(a>-b.terminal_brake) or np.any(u>-b.terminal_brake) or np.any(v>1e-5):
        raise RuntimeError('Backup does not reach the declared terminal braking tail')
    tail=up(up(v*v)/down(2*b.terminal_brake))
    yield up(q+tail)


def predecessor_envelope(v,a,b):
    """Lower displacement using acceleration's one-sided jerk bound."""
    v,a=np.broadcast_arrays(v,a);v=v.astype(float).copy();a=a.astype(float).copy()
    q=np.zeros_like(v);h=b.envelope_s
    yield q.copy()
    for _ in range(round(b.horizon_s/h)):
        a=np.maximum(-b.brake,down(a-up(b.actual_jerk_bound*h)))
        vn=np.maximum(0.,down(v+down(a*h)))
        q=down(q+down(h*np.minimum(v,vn)))
        q=np.maximum(q,0.);v=vn
        yield q.copy()


def upper32(x):return np.nextafter(np.asarray(x,dtype=np.float32),np.float32(np.inf))
def lower32(x):return np.nextafter(np.asarray(x,dtype=np.float32),np.float32(-np.inf))


def sum_upper(x):
    """Upper prefix sums for nonnegative binary64 inputs, n-roundoff bound."""
    n=x.shape[-1];gamma=float(up(n*2.**-53/down(1-n*2.**-53)))
    return up(np.cumsum(x,axis=-1)/down(1-gamma))


def sum_lower(x):
    n=x.shape[-1];gamma=float(up(n*2.**-53/down(1-n*2.**-53)))
    return np.maximum(0.,down(np.cumsum(x,axis=-1)/up(1+gamma)))


def ensure_tables(root,b=None):
    b=Bounds() if b is None else b;jerk=b.check();root=Path(root)
    final=root/f'braking-{b.key}'
    if (final/'certificate.json').is_file():
        meta=json.loads((final/'certificate.json').read_text())
        if meta['bounds']!=asdict(b) or meta['schema']!=2:raise RuntimeError('Proof-table bounds/schema mismatch')
        return final
    root.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix=f'.braking-{b.key}-',dir=root))
    aa,uu=axes(b);n=round(b.horizon_s/b.envelope_s);h=b.envelope_s
    ae,uc=np.meshgrid(aa,uu,indexing='ij');ae=ae.ravel();uc=uc.ravel()
    c5lo=exp_integral_bounds(h,b.eta_min)[0][0];c5hi=exp_integral_bounds(h,b.eta_max)[0][1]
    c3lo=exp_integral_bounds(h,b.eta_min)[1][0];c3hi=exp_integral_bounds(h,b.eta_max)[1][1]
    for prefix,name in [(False,'emergency'),(True,'nominal_block')]:
        out=np.lib.format.open_memmap(staging/f'{name}.npy',mode='w+',dtype='float64',shape=(len(ae),3,n+1))
        a=ae.copy();u=uc.copy();sl=np.zeros(len(a));sh=sl.copy();ch=sl.copy();curvature=sl.copy()
        out[:,:,0]=0.
        for k in range(n):
            in_prefix=prefix and k<round(b.guard_s/h)
            if in_prefix:u=np.minimum(b.acceleration_max,up(u+up(b.command_jerk*h)))
            positive=np.maximum(np.maximum(a,u),0.);difference=up(a-u)
            dv=up(up(h*u)+up(np.where(difference>=0,c3hi,c3lo)*difference))
            sl=down(sl+dv);sh=up(sh+dv)
            ch=np.maximum(ch,up(up(h*positive)-sl))
            curvature=up(curvature+up(up(.5*h*h)*positive))
            a=up(u+up(np.where(difference>=0,c5hi,c5lo)*difference))
            if not in_prefix:u=np.maximum(-b.brake,up(u-down(b.command_jerk*h)))
            out[:,0,k+1]=sh;out[:,1,k+1]=ch;out[:,2,k+1]=curvature
        maximum_v=up(sh+np.maximum(b.maximum_speed,ch))
        if np.any(a>-b.terminal_brake) or np.any(u>-b.terminal_brake) or np.any(maximum_v>1e-5):
            raise RuntimeError('Factorized envelope did not reach its terminal braking tail')
        out.flush();del out
    out=np.lib.format.open_memmap(staging/'predecessor.npy',mode='w+',dtype='float64',shape=(len(aa),n+1))
    a=aa.copy();s=np.zeros_like(a);out[:,0]=0.
    for k in range(n):
        a=np.maximum(-b.brake,down(a-up(b.actual_jerk_bound*h)))
        s=down(s+down(a*h));out[:,k+1]=s
    out.flush();del out
    hashes={p.name:hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in staging.glob('*.npy')}
    meta=dict(schema=2,bounds=asdict(b),table_id=b.key,actual_jerk_upper_from_command=jerk,
        array_hashes=hashes,ego_states=len(ae),predecessor_states=len(aa),
        proof='Outward interval arithmetic, monotone initial-state rounding, between-knot displacement enclosure, terminal stopping tail',
        assumptions='Bounded sensing, fixed positive actuator lag in declared range, bounded commands/command increments, valid initial backup certificate; see CERTIFIED_PROOFS.md')
    (staging/'certificate.json').write_text(json.dumps(meta,indent=2)+'\n')
    if final.exists():raise RuntimeError('An incomplete proof-table directory already exists; preserving it')
    os.rename(staging,final)
    return final


class Shield:
    def __init__(self,path,verify_hashes=True):
        path=Path(path);self.metadata=json.loads((path/'certificate.json').read_text())
        self.bounds=Bounds(**self.metadata['bounds']);self.bounds.check()
        if verify_hashes:
            for name,expected in self.metadata['array_hashes'].items():
                with (path/name).open('rb') as f:
                    if hashlib.file_digest(f,'sha256').hexdigest()!=expected:raise RuntimeError('Proof-table hash mismatch')
        if self.metadata['schema']!=2:raise ValueError('Unsupported proof-table schema')
        self.acceleration,self.command=axes(self.bounds)
        self.emergency=np.load(path/'emergency.npy',mmap_mode='r')
        self.nominal=np.load(path/'nominal_block.npy',mmap_mode='r')
        self.predecessor=np.load(path/'predecessor.npy',mmap_mode='r')

    def required_clearance(self,own_v_hi,own_a_hi,command,pred_v_lo,pred_a_lo,prefix=True):
        arrays=np.broadcast_arrays(own_v_hi,own_a_hi,command,pred_v_lo,pred_a_lo)
        shape=arrays[0].shape;v,a,u,pv,pa=[np.asarray(x).ravel() for x in arrays]
        valid=(np.isfinite(v)&np.isfinite(a)&np.isfinite(u)&np.isfinite(pv)&np.isfinite(pa)&
            (v>=0)&(v<=self.bounds.maximum_speed)&(pv>=0)&(pv<=self.bounds.maximum_speed)&
            (a>=self.acceleration[0])&(a<=self.acceleration[-1])&
            (pa>=self.acceleration[0])&(pa<=self.acceleration[-1])&
            (u>=self.command[0])&(u<=self.command[-1]))
        result=np.full(len(v),np.inf)
        if np.any(valid):
            ai=np.searchsorted(self.acceleration,a[valid],side='left')
            ui=np.searchsorted(self.command,u[valid],side='left')
            pai=np.searchsorted(self.acceleration,pa[valid],side='right')-1
            ego_index=ai*len(self.command)+ui
            factors=(self.nominal if prefix else self.emergency)[ego_index]
            velocities=np.maximum(0.,up(factors[:,0,:]+np.maximum(v[valid,None],factors[:,1,:])))
            ego=np.concatenate([np.zeros((len(ai),1)),up(sum_upper(up(self.bounds.envelope_s*velocities[:,:-1]))+factors[:,2,1:])],axis=1)
            tail=up(up(velocities[:,-1]**2)/down(2*self.bounds.terminal_brake))
            ego=np.concatenate([ego,up(ego[:,-1]+tail)[:,None]],axis=1)
            pred_velocities=np.maximum(0.,down(pv[valid,None]+self.predecessor[pai]))
            increments=down(self.bounds.envelope_s*np.minimum(pred_velocities[:,:-1],pred_velocities[:,1:]))
            pred=np.concatenate([np.zeros((len(ai),1)),sum_lower(np.maximum(0.,increments))],axis=1)
            # Ego at the end vs predecessor at the start encloses the entire
            # intervening interval; the final column covers all remaining time.
            closure=np.max(up(ego[:,1:]-pred),axis=1)
            result[valid]=up(self.bounds.minimum_clearance_m+np.maximum(closure,0.))
        return result.reshape(shape),valid.reshape(shape)

    def decide(self,d_lower,own_v_hi,own_a_hi,command,pred_v_lo,pred_a_lo,prefix=True):
        required,valid=self.required_clearance(own_v_hi,own_a_hi,command,pred_v_lo,pred_a_lo,prefix)
        margin=down(np.asarray(d_lower)-required)
        return valid&(margin>=0),margin
