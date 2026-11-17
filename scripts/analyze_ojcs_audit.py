#!/usr/bin/env python3
"""Read-only analysis of an exported diagnostic campaign; never reruns tasks.

Unlike the execution CLI, this accepts a different local runtime. It checks
manifest/task identities, result completeness and optional source-file hashes,
without requiring the analyst's OS/Python prefix to equal the cluster's.
These checks establish internal consistency, not independent authentication of
the supplied Slurm logs or correctness of the inherited scientific models.
"""
import argparse
import base64
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import statistics


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_campaign(manifest_path, source_root=None):
    """Fail closed on missing, extra, altered-identity or failed records."""
    manifest_path = Path(manifest_path).resolve()
    m = json.loads(manifest_path.read_text())
    header = {k: m[k] for k in ['schema', 'stage', 'preset', 'fingerprint', 'configs']}
    campaign = f'ojcs-{m["preset"]}-{digest(header)[:16]}'
    if m['schema'] != 1 or m['stage'] != 'synthetic_diagnostic' or m['campaign_id'] != campaign:
        raise ValueError('Manifest schema/stage/identity mismatch')
    if m['configs'] != [t['config'] for t in m['tasks']]:
        raise ValueError('Manifest configurations differ from tasks')
    tasks = {t['id']: t for t in m['tasks']}
    if len(tasks) != len(m['tasks']) or any(k != digest(t['config'])[:20] for k, t in tasks.items()):
        raise ValueError('Duplicate or invalid task identity')
    base = manifest_path.parent.parent / campaign
    paths = list((base/'results').glob('*.json'))
    if {p.name for p in paths} != {f'{k}.json' for k in tasks}:
        raise ValueError('Missing, extra or failed result files')
    records = []
    for p in sorted(paths):
        r = json.loads(p.read_text())
        k = p.stem
        if (r['id'] != k or r['campaign_id'] != campaign or r['config'] != tasks[k]['config']
                or r['status'] != 'complete' or r['stage'] != 'synthetic_diagnostic'):
            raise ValueError(f'Result identity/status mismatch: {p.name}')
        canonical(r)  # Reject non-finite JSON values as well.
        records.append(r)
    summary = json.loads((base/'summary.json').read_text())
    expected = Counter(r['config']['family'] for r in records)
    if (summary['campaign_id'] != campaign or summary['expected'] != len(records)
            or summary['complete'] != len(records) or summary['failed'] or summary['pending']
            or set(summary['families']) != set(expected)):
        raise ValueError('Summary completeness/identity mismatch')
    for family, n in expected.items():
        if summary['families'][family] != dict(expected=n, complete=n, failed=0, pending=0):
            raise ValueError('Summary family counts mismatch')
    if not math.isclose(summary['diagnostic_cpu_s'], sum(r['cpu_s'] for r in records), abs_tol=1e-6):
        raise ValueError('Summary CPU accounting mismatch')
    if not math.isclose(summary['maximum_observed_process_rss_mb'],
                        max(r['process_peak_rss_mb'] for r in records), abs_tol=1e-6):
        raise ValueError('Summary memory accounting mismatch')
    checked = []
    if source_root is not None:
        root = Path(source_root).resolve()
        for name, expected_hash in m['fingerprint']['files'].items():
            p = (root/name).resolve()
            if not p.is_relative_to(root) or not p.is_file():
                raise ValueError(f'Missing or external source/input: {name}')
            if hashlib.sha256(p.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f'Source/input hash mismatch: {name}')
            checked.append(name)
    verification = dict(campaign_id=campaign, records=len(records), family_counts=dict(expected),
                        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                        source_files_checked=len(checked), runtime=m['fingerprint']['runtime'],
                        dependencies=m['fingerprint']['versions'],
                        result_content_digest=digest(records),
                        scope='Internal consistency and optional file-hash checks; not external attestation')
    return m, records, summary, verification


def mean_ci(values):
    """Exploratory two-sided t interval across independent seed clusters."""
    values = list(values)
    avg = statistics.mean(values)
    interval = None
    if len(values) > 1:
        from scipy.stats import t
        half = float(t.ppf(.975, len(values)-1))*statistics.stdev(values)/math.sqrt(len(values))
        interval = [avg-half, avg+half]
    return dict(mean=avg, seed_clusters=len(values), seed_values=values,
                exploratory_seed_t_95=interval)


def describe(values):
    values = list(values)
    return None if not values else dict(n=len(values), minimum=min(values),
                                        median=statistics.median(values), maximum=max(values))


def group(records, exclude):
    groups = defaultdict(list)
    for r in records:
        key = canonical({k: v for k, v in r['config'].items() if k not in exclude})
        groups[key].append(r)
    return [(json.loads(k), sorted(v, key=lambda r: r['config'].get('seed', 0)))
            for k, v in sorted(groups.items())]


def radio_analysis(records):
    supported = [r for r in records if r['metrics']['supported']]
    strata = []
    for config, rows in group(supported, {'family', 'h', 'beta', 'eta', 'n_trucks', 'payload', 'rice'}):
        counts = {}
        for target in ['descriptor_A', 'fixed_9999']:
            vals = [r['metrics']['comparison'][target] for r in rows]
            counts[target] = dict(inherited_fits=sum(v['inherited_plan_fits_slot'] for v in vals),
                capped_feasible=sum(v['capped_plans']['power_aware'] is not None for v in vals))
        joint = [r for r in rows if all(r['metrics']['comparison'][k]['capped_plans']['power_aware']
                                      is not None for k in ['descriptor_A', 'fixed_9999'])]
        savings = [1-r['metrics']['comparison']['descriptor_A']['capped_plans']['power_aware']['prb_slots']
                     /r['metrics']['comparison']['fixed_9999']['capped_plans']['power_aware']['prb_slots']
                   for r in joint]
        strata.append(dict(**config, supported_cases=len(rows), targets=counts,
                           savings_jointly_feasible=describe(savings), jointly_feasible_ids=[r['id'] for r in joint]))
    changed = []
    for r in supported:
        for name, v in r['metrics']['comparison'].items():
            if v['capped_plans']['power_aware'] != v['capped_plans']['fixed_reference_sinr']:
                changed.append(dict(id=r['id'], target=name, config=r['config'], plans=v['capped_plans']))
    return dict(total=len(records), supported=len(supported), unavailable=len(records)-len(supported),
                unavailable_configs=[c for c, _ in group([r for r in records if not r['metrics']['supported']],
                     {'family', 'n_trucks', 'blocked', 'payload', 'rice', 'cap'})],
                strata=strata, power_model_changed_plans=changed,
                interpretation='Per-copy slot cap only; no multi-link schedule is validated by this experiment. '
                'Missing capped plans mean none found within 1-4 one-slot copies, not physical impossibility. '
                'Savings are deterministic grid descriptions restricted to jointly feasible cases.')


def fading_analysis(records):
    cells = []
    for c, rows in group(records, {'family', 'seed', 'replicates'}):
        for i, attempts in enumerate([1, 2, 4]):
            losses = [r['metrics']['rows'][i]['loss_estimate'] for r in rows]
            cells.append(dict(**c, attempts=attempts, loss=mean_ci(losses),
                mean_marginal_product=statistics.mean(r['metrics']['rows'][i]['product_of_marginal_error_estimates'] for r in rows),
                replicates_per_seed=sorted({r['config']['replicates'] for r in rows}),
                ids=[r['id'] for r in rows]))
    example = [c for c in cells if c['h'] == 1. and c['b'] == 80 and c['rice'] == 3.]
    paired = {}
    by_rho = {c['rho']: c for c in example if c['attempts'] == 4}
    if 0. in by_rho:
        for rho in [.5, .9, 1.]:
            if rho in by_rho:
                paired[str(rho)] = mean_ci(a-b for a, b in zip(by_rho[rho]['loss']['seed_values'],
                                                             by_rho[0.]['loss']['seed_values']))
    return dict(total=len(records), cells=cells, representative_h1_b80_k3=example,
                paired_absolute_four_copy_loss_increase_vs_rho0=paired,
                interpretation='rho correlates synthetic diffuse fading across copies. Conditional decoder '
                'errors remain independent. Four seed clusters per audit cell; intervals are exploratory, '
                'pointwise and unadjusted. Near-zero estimates do not certify rare-event reliability.')


def control_analysis(records):
    supported = [r for r in records if r['metrics']['supported']]
    cells = []
    for c, rows in group(supported, {'family', 'seed', 'replicates'}):
        events = sum(r['metrics']['growth_events'] for r in rows)
        reps = sum(r['metrics']['braking_events'] for r in rows)
        cells.append(dict(**c, events=events, episodes=reps, event_fraction=events/reps,
             seed_event_fractions=mean_ci(r['metrics']['event_fraction'] for r in rows),
             mean_square_pulse_gain=math.sqrt(sum(r['metrics']['mean_square_pulse_gain']**2*
                                               r['metrics']['braking_events'] for r in rows)/reps),
             finite_platoon_gain_bound=rows[0]['metrics']['finite_platoon_gain_bound'],
             ids=[r['id'] for r in rows]))
    effects = []
    for rho in sorted({r['config']['rho'] for r in supported}):
        selected = [r for r in supported if r['config']['rho'] == rho]
        per_margin = {}
        for margin in [0., -.05]:
            by_seed = defaultdict(list)
            for r in selected:
                if r['config']['delivery_margin'] == margin:
                    by_seed[r['config']['seed']].append(r['metrics']['event_fraction'])
            per_margin[margin] = {s: statistics.mean(v) for s, v in by_seed.items()}
        common = sorted(set(per_margin[0.]) & set(per_margin[-.05]))
        effects.append(dict(rho=rho,
            at_descriptor=mean_ci(per_margin[0.][s] for s in common),
            below_descriptor=mean_ci(per_margin[-.05][s] for s in common),
            paired_margin_effect=mean_ci(per_margin[-.05][s]-per_margin[0.][s] for s in common)))
    return dict(total=len(records), supported=len(supported), unavailable=len(records)-len(supported),
        unavailable_configs=[c for c, _ in group([r for r in records if not r['metrics']['supported']],
             {'family', 'n_trucks', 'rho', 'delivery_margin', 'brake', 'seed', 'replicates'})],
        cells=cells, grid_average_margin_effects=effects,
        per_record_pulse_gain=describe(r['metrics']['mean_square_pulse_gain'] for r in supported),
        sampled_pulse_gain_above_bound=sum(r['metrics']['mean_square_pulse_gain'] >
                                          r['metrics']['finite_platoon_gain_bound'] for r in supported),
        observed_nonpositive_distance=sum(r['metrics']['observed_nonpositive_distance'] for r in supported),
        minimum_record_01_distance_quantile_m=min(r['metrics']['minimum_distance_01_quantile_m'] for r in supported),
        interpretation='Type A bounds mean-square command-energy gain, not the probability of peak '
        'spacing-error growth above 5%. Pulse tests over 12 s are not induced-norm certificates. '
        'Cross-link-correlated cases are outside the inherited independent-link composition argument. '
        'Seed reuse across the grid is handled by averaging within each seed before forming paired '
        'exploratory t intervals; the grid is not a sampled deployment distribution. No collision guarantee.')


def market_analysis(records):
    rows = []
    for r in records:
        c, v = r['config'], r['metrics']
        exact = v['exact_reference']
        optimum = exact['incremental_utility'] if exact and exact['proven_optimal'] else None
        rows.append(dict(**c, id=r['id'], exact_proven=bool(exact and exact['proven_optimal']),
            incremental_ratio_exact=None if optimum is None or optimum <= 1e-12 else v['incremental_utility']/optimum,
            total_ratio_exact=None if optimum is None else v['market']['utility']/(optimum+v['acc_utility']),
            incremental_ratio_lp=v['incremental_ratio_to_lp_upper_bound'],
            advantage_vs_fixed=v['market']['utility']-v['fixed']['utility'],
            menu_build_s=v['menu_build_s'], market_s=v['market_s'], price_rounds=v['price_rounds'],
            exact_s=exact['runtime_s'] if exact else None,
            feasible=v['market']['feasible'] and v['fixed']['feasible']))
    strata = []
    for c, rs in group(records, {'family', 'pool', 'seed'}):
        ids = {r['id'] for r in rs}
        selected = [r for r in rows if r['id'] in ids]
        strata.append(dict(**c,
            incremental_ratio_exact=describe(r['incremental_ratio_exact'] for r in selected if r['incremental_ratio_exact'] is not None),
            total_ratio_exact=describe(r['total_ratio_exact'] for r in selected if r['total_ratio_exact'] is not None),
            menu_build_s=describe(r['menu_build_s'] for r in selected),
            market_s=describe(r['market_s'] for r in selected),
            exact_s=describe(r['exact_s'] for r in selected if r['exact_s'] is not None)))
    return dict(total=len(rows), proven_optimal_references=sum(r['exact_proven'] for r in rows),
        all_allocations_feasible=all(r['feasible'] for r in rows), rows=rows, strata=strata,
        interpretation='Same inherited abstract resource model and illustrative utility, not checked '
        'sidelink schedules. Exact ratios use only solver-proven optima. ACC-relative utility is the '
        'primary ratio; the ACC offset inflates total-utility ratios. Menu times depend on process-local '
        'cache history; market and MILP times exclude menu generation and do not measure network signaling. '
        'Fixed-gap admission offers fewer options. No universal approximation or privacy guarantee follows.')


def resource_analysis(records, cpus=None, job_wall_s=None, worker_wall_s=None):
    ranks = []
    for rank in sorted({r['rank'] for r in records}):
        rr = [r for r in records if r['rank'] == rank]
        ranks.append(dict(rank=rank, tasks=len(rr), task_wall_s=sum(r['wall_s'] for r in rr),
                          task_cpu_s=sum(r['cpu_s'] for r in rr)))
    costs = {}
    for family in sorted({r['config']['family'] for r in records}):
        rr = [r for r in records if r['config']['family'] == family]
        costs[family] = dict(cpu_s=sum(r['cpu_s'] for r in rr), task_wall_s=sum(r['wall_s'] for r in rr))
    cpu = sum(r['cpu_s'] for r in records)
    return dict(by_family=costs, ranks=ranks, hosts=dict(Counter(r['hostname'] for r in records)),
        task_cpu_s=cpu, peak_process_rss_mib=max(r['process_peak_rss_mb'] for r in records),
        task_cpu_fraction_of_job_allocation=None if not cpus or not job_wall_s else cpu/(cpus*job_wall_s),
        task_cpu_fraction_of_worker_allocation=None if not cpus or not worker_wall_s else cpu/(cpus*worker_wall_s),
        static_shard_wall_balance=sum(r['task_wall_s'] for r in ranks)/(len(ranks)*max(r['task_wall_s'] for r in ranks)),
        supplied_accounting=dict(cpus=cpus, job_wall_s=job_wall_s, worker_wall_s=worker_wall_s),
        interpretation='Per-task process CPU excludes imports, tests and setup. ru_maxrss is a cumulative '
        'per-process peak, not simultaneous aggregate memory. One host does not validate multi-node behavior. '
        'Static shard sums and menu timings include cache-history effects.')


def flatten(value, prefix=''):
    out = {}
    for k, v in value.items():
        key = prefix+k
        if isinstance(v, dict):
            out.update(flatten(v, key+'.'))
        else:
            out[key] = canonical(v) if isinstance(v, list) else v
    return out


def write_csv(path, rows):
    rows = [flatten(r) for r in rows]
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, sorted({k for r in rows for k in r}))
        writer.writeheader()
        writer.writerows(rows)


def figures(data, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none'})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.7), layout='constrained')
    ax = axes[0, 0]
    strata = sorted(data['radio']['strata'], key=lambda s: (s['blocked'], s['cap']))
    x = np.arange(len(strata))
    for shift, target, label, color in [(-.19, 'descriptor_A', 'Type-A target', '#007f8b'),
                                       (.19, 'fixed_9999', '99.99% target', '#cf5f30')]:
        ax.bar(x+shift, [100*s['targets'][target]['capped_feasible']/s['supported_cases'] for s in strata],
               .36, label=label, color=color)
    ax.set(xticks=x, xticklabels=[f'{s["cap"]} PRBs\n'+('Blocked' if s['blocked'] else 'LOS') for s in strata],
           ylabel='Feasible grid cases (%)', ylim=(0, 110), title='A. One-slot-copy bandwidth cap')
    ax.legend(fontsize=9)
    ax = axes[0, 1]
    for rho, color in [(0., '#007f8b'), (.5, '#57803b'), (.9, '#cf5f30'), (1., '#80539b')]:
        cells = sorted([c for c in data['fading']['representative_h1_b80_k3'] if c['rho'] == rho], key=lambda c:c['attempts'])
        if not cells:
            continue
        y = [100*c['loss']['mean'] for c in cells]
        half = [100*(c['loss']['exploratory_seed_t_95'][1]-c['loss']['mean']) for c in cells]
        ax.errorbar([c['attempts'] for c in cells], y, yerr=half, marker='o', capsize=3,
                    color=color, label=f'ρ = {rho:g}')
    ax.set(xticks=[1, 2, 4], xlabel='Blind copies', ylabel='Joint packet loss (%)',
           title='B. Correlated fading: h=1 s, b=80, K=3 dB')
    ax.legend(fontsize=9)
    ax = axes[1, 0]
    cells = [c for c in data['control']['cells'] if c['n_trucks']==3 and c['h']==1. and c['beta']==4. and c['brake']=='hard']
    for margin, label, color in [(0., 'At Type-A target', '#007f8b'), (-.05, 'Target − 0.05', '#cf5f30')]:
        cc = sorted([c for c in cells if c['delivery_margin']==margin], key=lambda c:c['rho'])
        if not cc:
            continue
        y = [100*c['seed_event_fractions']['mean'] for c in cc]
        half = [100*(c['seed_event_fractions']['exploratory_seed_t_95'][1]-c['seed_event_fractions']['mean']) for c in cc]
        ax.errorbar([c['rho'] for c in cc], y, yerr=half, marker='o', capsize=3, label=label, color=color)
    ax.set(xticks=[0, .5, .9], xlabel='Latent cross-link correlation ρ', ylabel='Peak-spacing growth > 5% (%)',
           title='C. Peak-spacing risk differs from energy gain')
    ax.legend(fontsize=9)
    ax = axes[1, 1]
    selected = [s for s in data['market']['strata'] if s['incremental_ratio_exact']]
    for contract, color, shift in [('A', '#007f8b', -.06), ('B', '#cf5f30', .06)]:
        ss = sorted([s for s in selected if s['contract']==contract], key=lambda s:s['tenants'])
        x = np.arange(len(ss))+shift
        y = [100*s['incremental_ratio_exact']['median'] for s in ss]
        ax.errorbar(x, y, yerr=[[v-100*s['incremental_ratio_exact']['minimum'] for v,s in zip(y,ss)],
                               [100*s['incremental_ratio_exact']['maximum']-v for v,s in zip(y,ss)]],
                    marker='o', capsize=4, color=color, label=f'Type {contract}')
    ns = sorted({s['tenants'] for s in selected})
    ax.set(xticks=np.arange(len(ns)), xticklabels=ns, xlabel='Tenants', ylabel='ACC-relative utility / exact optimum (%)',
           ylim=(89, 101), title='D. Market: median and range across 12 cases')
    ax.legend(fontsize=9)
    fig.suptitle(f'HPC audit {data["execution"]["attempt"]} · synthetic diagnostics of inherited models', fontsize=14)
    for suffix in ['png', 'svg']:
        fig.savefig(output/f'audit_findings.{suffix}', dpi=180)
    plt.close(fig)


def report_html(data, output):
    def table(headers, rows):
        return '<table><tr>'+''.join(f'<th>{html.escape(str(h))}</th>' for h in headers)+'</tr>'+''.join(
            '<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in r)+'</tr>' for r in rows)+'</table>'
    radio_rows = []
    for s in data['radio']['strata']:
        n = s['supported_cases']
        joint = s['savings_jointly_feasible']
        radio_rows.append([s['cap'], 'Blocked' if s['blocked'] else 'LOS', n,
            s['targets']['descriptor_A']['inherited_fits'], s['targets']['descriptor_A']['capped_feasible'],
            s['targets']['fixed_9999']['capped_feasible'], 0 if joint is None else joint['n'],
            '—' if joint is None else f'{100*joint["median"]:.1f}%'])
    example = [c for c in data['fading']['representative_h1_b80_k3'] if c['attempts']==4]
    fade_rows = [[c['rho'], f'{100*c["loss"]["mean"]:.3f}%',
                  ' – '.join(f'{100*v:.3f}%' for v in c['loss']['exploratory_seed_t_95'])] for c in example]
    market_rows = []
    for s in data['market']['strata']:
        q=s['incremental_ratio_exact']
        if q:
            market_rows.append([s['contract'], s['tenants'], f'{100*q["median"]:.2f}%', f'{100*q["minimum"]:.2f}%',
                f'{s["menu_build_s"]["median"]:.3f}', f'{1000*s["market_s"]["median"]:.2f}', f'{1000*s["exact_s"]["median"]:.2f}'])
    control=data['control']
    worst = sorted(control['cells'], key=lambda c:c['event_fraction'], reverse=True)[0]
    independent = sorted([c for c in control['cells'] if c['rho']==0 and c['delivery_margin']==0],
                         key=lambda c:c['event_fraction'], reverse=True)[0]
    res=data['resources']
    execution=data['execution']
    unavailable=data['radio']['unavailable']+data['control']['unavailable']
    supplied=res['supplied_accounting']
    accounting_text = ('No elapsed-time accounting was supplied.' if supplied['job_wall_s'] is None else
                       f'Supplied accounting reports {supplied["job_wall_s"]:g} s total elapsed time.')
    if supplied['worker_wall_s'] is not None:
        accounting_text += f' The worker step took {supplied["worker_wall_s"]:g} s.'
    costs=table(['Family', 'Task CPU seconds', 'CPU fraction'], [[k, f'{v["cpu_s"]:.2f}',
                f'{100*v["cpu_s"]/res["task_cpu_s"]:.2f}%'] for k,v in res['by_family'].items()])
    image_data=base64.b64encode((output/'audit_findings.png').read_bytes()).decode()
    text=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>GapSlice diagnostic audit analysis</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#172d39;max-width:1120px;margin:40px auto;padding:0 24px}}
h1,h2{{line-height:1.2}}h2{{margin-top:2em}}table{{border-collapse:collapse;font-size:14px;width:100%;margin:20px 0}}
td,th{{text-align:left;padding:9px;border-bottom:1px solid #ccd6dc}}th{{background:#eef4f5}}img{{width:100%}}
.note{{border-left:4px solid #cf5f30;background:#fff7ee;padding:12px 18px}}code{{overflow-wrap:anywhere}}
@media print{{body{{font-size:11px;margin:0;max-width:none}}h2{{break-after:avoid}}tr,img{{break-inside:avoid}}}}</style>
<h1>GapSlice: diagnostic evidence and revision decisions</h1>
<p>Campaign <code>{data['verification']['campaign_id']}</code> · execution {execution['attempt']} · analysis {execution['analysis_utc']}</p>
<p class="note">All {data['verification']['records']:,} tasks completed, but {unavailable} tasks report unavailable inherited descriptors.
These are synthetic diagnostics, not validation of the proposed revised method. Do not launch the full
diagnostic grid merely to increase the experiment count.</p>
<p>Verified task identities, completeness, summary accounting and
{data['verification']['source_files_checked']} source/input SHA-256 hashes. These are internal provenance
checks against the supplied export, not independent authentication of the cluster execution.</p>
<img alt="Four panels showing radio feasibility, correlated fading losses, spacing-growth risk and market utility ratios" src="data:image/png;base64,{image_data}">
<p>Panels B/C show exploratory 95% t intervals across four seed clusters; panel D shows the observed
range, not a confidence interval. Panel C fixes h=1 s, β=4, N=3 and hard braking; it is a selected
stress case, not an average over the full grid.</p>
<h2>1. Radio: rebuild feasibility before reporting savings</h2>
<p>{data['radio']['supported']} of {data['radio']['total']} cases have a finite Type-A descriptor.
The other {data['radio']['unavailable']} cases are descriptor-unavailable, not execution failures.
The table counts supported parameter-grid cases; it is not a deployment success probability.</p>
{table(['PRB cap','Channel','Cases','Inherited A plan fits','Capped A feasible','Capped 99.99% feasible','Joint cases','Median joint savings'], radio_rows)}
<p>Blocked-link failures dominate these one-slot-copy configurations. A different admissible split can rescue
some inherited optimum plans that exceed the bandwidth cap. Empty plans mean no solution within the tested
1–4 one-slot copies, not impossibility under all sidelink designs. The radio experiment checks per-copy
bandwidth; it does not run the separate multi-link schedule checker.</p>
<p>Only {len(data['radio']['power_model_changed_plans'])} of {2*data['radio']['supported']} target/configuration
plan pairs change under the allocation-dependent noise ablation. Fixed coextensive interferers keep this
model largely interference-limited. This does not validate the general fixed-SINR assumption.</p>
<p><b>Decision:</b> implement discrete payload/MCS/overhead accounting, checked slot assignments, deadline and
half-duplex constraints, and schedule-dependent interference. Compare resource costs only when both methods
meet the same outcome and scheduling conditions; report feasible coverage separately.</p>
<h2>2. Repeated transmissions: independence is a consequential assumption</h2>
<p>Illustrative fixed cell: gap 1 s, 80 PRBs per copy, Rician K=3 dB, four copies,
four independent seeds with 20,000 fading realizations each. Intervals below are exploratory seed-level
t intervals (3 degrees of freedom), pointwise and unadjusted.</p>
{table(['Diffuse correlation ρ','Mean four-copy loss','Exploratory 95% interval'], fade_rows)}
<p>{html.escape(data['fading']['interpretation'])}</p>
<p><b>Decision:</b> replace unqualified independent-copy reliability with a declared, calibrated correlation
and coherence model; test hopping/interleaving and repetition under equal time, bandwidth and energy budgets.
Do not use this small Monte Carlo campaign to certify 99.99% reliability.</p>
<h2>3. Control: distinguish the promised outcome from a different metric</h2>
<p>{control['supported']} of {control['total']} configurations ran the inherited fixed-gap model;
{control['unavailable']} report unavailable descriptors. The sampled mean-square pulse-gain estimates range
from {control['per_record_pulse_gain']['minimum']:.3f} to {control['per_record_pulse_gain']['maximum']:.3f};
{control['sampled_pulse_gain_above_bound']} exceed the corresponding finite-platoon bound.</p>
<p>Peak spacing-error growth above 5% still occurs. The highest grouped observed rate is
{worst['events']}/{worst['episodes']} ({100*worst['event_fraction']:.2f}%) at h={worst['h']} s,
β={worst['beta']}, N={worst['n_trucks']}, ρ={worst['rho']}, delivery margin={worst['delivery_margin']},
{worst['brake']} braking. Within independent-link, at-descriptor cases, the highest observed cell is
{independent['events']}/{independent['episodes']} ({100*independent['event_fraction']:.2f}%). These are
post hoc exploratory selections. Type A is an energy-gain condition, so these peak-event rates do not by
themselves refute its certificate. They show why it must not be described as a peak-risk guarantee.</p>
<p>{html.escape(control['interpretation'])} No nonpositive distances were observed in this tested linear,
ideal-radar regime. That observation does not certify braking safety, realistic actuator behavior,
delay tolerance or full gap-changing maneuvers.</p>
<p><b>Decision:</b> specify one primary contract and the exact signal/norm, platoon length and uncertainty
assumptions; independently re-solve selected certificate points, use broader disturbances and longer horizons,
and account for packet age, actuator constraints and the complete reconfiguration transient. Keep event-risk
and energy-gain contracts separate.</p>
<h2>4. Allocation: promising in this abstraction; limited evidence for a new contribution</h2>
<p>All {data['market']['proven_optimal_references']} MILP references are reported solver-optimal, and all
market/fixed allocations satisfy the abstract pool capacity. Ratios below use utility above ACC;
each row summarizes 12 instances (three pools × four seeds).</p>
{table(['Contract','Tenants','Median / exact','Minimum / exact','Menu median (s)','Market median (ms)','MILP median (ms)'], market_rows)}
<p>{html.escape(data['market']['interpretation'])}</p>
<p><b>Decision:</b> retain the market as a supporting mechanism unless revised experiments establish a
distinct computing contribution. Evaluate it against simple matched menu-allocation policies and a
full-information optimizer, separate offline menu/certificate preparation from online allocation, and
measure messages and inference leakage if communication/privacy claims are retained. These small cases
do not establish a need for GPU training or a more elaborate learned allocator.</p>
<h2>5. Compute: parallel execution works; task costs are very uneven</h2>
{costs}
<p>{accounting_text} All results came
from {html.escape(', '.join(res['hosts']))}. Recorded task CPU totals {res['task_cpu_s']:.2f} s.
The maximum cumulative process RSS is {res['peak_process_rss_mib']:.2f} MiB; this is not aggregate job memory.
Static rank task-wall sums range from {min(r['task_wall_s'] for r in res['ranks']):.2f} to
{max(r['task_wall_s'] for r in res['ranks']):.2f} s, with balance
{100*res['static_shard_wall_balance']:.1f}%. Market menu creation dominates; caching differs across ranks.</p>
<p><b>Decision:</b> profile the rebuilt pipeline before choosing worker counts and queue limits.
Use cost-aware or dynamic work distribution for later heterogeneous campaigns and report preprocessing
costs explicitly. Multi-node behavior is still unverified. Do not extrapolate these runtimes to the
not-yet-implemented revised PHY/control system.</p>
<h2>Next research gate</h2>
<ol><li>Freeze these inherited-model diagnostics and preserve negative cases.</li>
<li>Build and verify the coupled resource planner and precise control contract.</li>
<li>Validate complete reconfiguration and select an independent, feature-compatible backend.</li>
<li>Freeze matched baselines, uncertainty assumptions, train/test separation where applicable and the
final statistical protocol, then use HPC for the final study.</li></ol>
<p>Unverified: measured/testbed evidence, independent NR validation, a new control or safety proof,
formal privacy guarantees, final-method comparisons and a submission-ready manuscript.
Current diagnostics do not establish journal acceptance or paper tier.</p>
<h2>Reproducibility files</h2>
<p><a href="analysis.json">Machine-readable analysis</a> · <a href="records.csv">All task metrics</a> ·
<a href="radio_strata.csv">Radio strata</a> · <a href="fading_cells.csv">Fading cells</a> ·
<a href="control_cells.csv">Control cells</a> · <a href="market_instances.csv">Market instances</a> ·
<a href="audit_findings.svg">Vector figure</a></p>
<p>Per-cell result IDs in the analysis and CSV files trace back to the supplied immutable manifest.
Raw results stay unchanged. The analysis script generates no new simulation evidence.</p></html>'''
    (output/'report.html').write_text(text)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cpus', type=int)
    parser.add_argument('--job-wall-s', type=float)
    parser.add_argument('--worker-wall-s', type=float)
    args=parser.parse_args()
    output=args.output.resolve()
    input_root=args.manifest.resolve().parent.parent
    if output.is_relative_to(input_root) or input_root.is_relative_to(output):
        parser.error('Analysis output must be separate from the exported inputs')
    m, records, summary, verification=load_campaign(args.manifest, args.source_root)
    if m['preset'] != 'audit':
        parser.error('The report template is for the audit preset')
    by_family={f:[r for r in records if r['config']['family']==f] for f in ['radio','fading','control','market']}
    if any(not rows for rows in by_family.values()):
        parser.error('This analysis requires all four diagnostic families')
    verification['analysis_implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    data=dict(verification=verification,
              execution=dict(attempt=summary['attempt'], analysis_utc=datetime.now(timezone.utc).isoformat()),
              radio=radio_analysis(by_family['radio']),
              fading=fading_analysis(by_family['fading']), control=control_analysis(by_family['control']),
              market=market_analysis(by_family['market']),
              resources=resource_analysis(records, args.cpus, args.job_wall_s, args.worker_wall_s))
    output.mkdir(parents=True, exist_ok=True)
    (output/'analysis.json').write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    write_csv(output/'records.csv', records)
    for name, rows in [('radio_strata',data['radio']['strata']),('fading_cells',data['fading']['cells']),
                       ('control_cells',data['control']['cells']),('market_instances',data['market']['rows'])]:
        write_csv(output/f'{name}.csv', rows)
    figures(data, output)
    report_html(data, output)
    print(json.dumps(dict(report=str(output/'report.html'), verified=verification['records'],
                           source_files_checked=verification['source_files_checked']), indent=2))


if __name__ == '__main__':
    main()
