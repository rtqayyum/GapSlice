"""Published Max-C/I, PF and DRR cores on one common packet test harness.

The common half-duplex/deadline veto is an explicit sidelink adaptation.
This benchmark is packet-level; it is not a reproduction of Mandal et al.'s
OMNeT++ architecture or an end-to-end controller comparison.
"""
from collections import deque
import numpy as np


def select(method,eligible,rates,average,deficit,pointer):
    if not eligible:return None
    if method=='maxci':return max(eligible,key=lambda i:(rates[i],-i))
    if method=='pf':return max(eligible,key=lambda i:(rates[i]/max(average[i],1e-12),-i))
    if method=='drr':
        for offset in range(len(rates)):
            i=(pointer+offset)%len(rates)
            if i in eligible and deficit[i]>=300:return i
        return None
    raise ValueError('Unknown scheduler')


def benchmark(seed,links,cap,method,slots=4000):
    random=np.random.default_rng(seed)
    # All policies receive identical per-link channel and arrival arrays.
    rates=np.log2(1+10**(random.normal(5,6,(slots,links))/10))
    arrivals=random.random((slots,links))<.015
    queues=[deque() for _ in range(links)];average=np.full(links,1e-3)
    deficit=np.zeros(links);pointer=0;sent=np.zeros(links);lost=0;created=0;delays=[]
    quantum=300.;delivered=np.zeros(links)
    for tick in range(slots):
        for i in range(links):
            if arrivals[tick,i]:queues[i].append(tick);created+=1
            while queues[i] and tick-queues[i][0]>=18:queues[i].popleft();lost+=1
        if tick%links==0:deficit+=quantum  # One quantum per cyclic round.
        endpoints=set();served=np.zeros(links)
        for _ in range(cap//10):
            eligible=[i for i in range(links) if queues[i] and i not in endpoints and i+1 not in endpoints]
            i=select(method,eligible,rates[tick],average,deficit,pointer)
            if i is None:break
            # Abstract capacity: 10 PRBs x 120 RE x spectral efficiency.
            if 1200*rates[tick,i]<2400:eligible.remove(i);endpoints|={i,i+1};continue
            release=queues[i].popleft();delays.append((tick-release+.999)*.5)
            served[i]=2400.;sent[i]+=1;delivered[i]+=300.;endpoints|={i,i+1}
            deficit[i]-=300;pointer=(i+1)%links
        average=(1-1/100)*average+served/100
        # Empty-queue deficits are reset, as in standard DRR.
        for i in range(links):
            if not queues[i]:deficit[i]=0
    pending=sum(map(len,queues));fairness=float(sent.sum()**2/(links*np.sum(sent**2))) if np.any(sent) else 0.
    return dict(seed=seed,links=links,cap=cap,method=method,created=created,delivered=int(sent.sum()),
                expired=lost,right_censored_pending=pending,delivery_ratio=float(sent.sum()/max(created,1)),
                delay_p95_ms=float(np.quantile(delays,.95)) if delays else None,jain_fairness=fairness,
                scope='Abstract packet-only published scheduler cores with common feasibility veto; not end-to-end control evidence')
