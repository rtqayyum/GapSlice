"""Standalone scientific figures from committed summaries, no new simulation."""
from pathlib import Path
import numpy as np


def create(base,study,rows,qualification,allocations):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    base=Path(base);bank={c['id']:c for c in study['candidate_bank']}
    colors=dict(fused='#1565c0',hold='#d36135',radar='#18886c',fused_parallel='#8e5b9a',fused_synchronous='#797979')
    figure,axes=plt.subplots(1,3,figsize=(14,4.2),layout='constrained')
    for mode in ['fused','hold','radar']:
        cells=[r for r in rows if bank[r['candidate_id']]['policy']['controller']==mode]
        x=[];y=[]
        for r in cells:
            p=bank[r['candidate_id']]['profile'];maximum=p['h_initial']-p['h_target']
            x.append(r['reward_sum']/r['n']/maximum if maximum>0 else 0);y.append(100*r['k']/r['n'])
        axes[0].scatter(x,y,s=7,alpha=.25,color=colors[mode],label=mode)
    axes[0].set(xlabel='Held-out achieved gain / contract gain',ylabel='Held-out episode failures (%)',title='All frozen candidate cells')
    axes[0].axhline(1,color='black',lw=.7,ls='--');axes[0].legend(fontsize=8)
    domains=list(study['protocol']['domains']);xx=np.arange(len(domains))
    for j,mode in enumerate(['fused','hold','radar']):
        counts=[sum(r['qualified'] and r['domain']==d and r['candidate']['policy']['controller']==mode for r in qualification['records']) for d in domains]
        axes[1].bar(xx+(j-1)*.24,counts,width=.24,label=mode,color=colors[mode])
    axes[1].set(xticks=xx,xticklabels=domains,ylabel='Qualified candidate/domain records',title='Calibration qualification')
    domain='los' if 'los' in domains else domains[0]
    for variant,color in colors.items():
        cells=sorted([r for r in allocations if r['scenario']['cap']==51 and r['scenario']['domain']==domain
            and r['scenario']['method']=='exact' and r['scenario']['variant']==variant],key=lambda r:r['scenario']['tenants'])
        axes[2].plot([r['scenario']['tenants'] for r in cells],[r['benefit_microseconds']/1e6 for r in cells],
            marker='o',ms=3,color=color,label=variant)
    axes[2].set(xlabel='Offered tenants',ylabel='Sum of benefit lower bounds (s)',title=f'51 PRBs; {domain}; checked MILP incumbent')
    axes[2].legend(fontsize=7)
    axes[0].set_xlim(0,1)
    for ax in axes:ax.grid(alpha=.17);ax.set_axisbelow(True);ax.set_ylim(bottom=0)
    for suffix in ['png','svg']:figure.savefig(base/f'study_overview.{suffix}',dpi=180)
    plt.close(figure)
