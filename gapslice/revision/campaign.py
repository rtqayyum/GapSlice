"""Resumable independent-worker campaigns for the OJ-CS diagnostic stage.

python -m gapslice.revision.campaign build --preset smoke
python -m gapslice.revision.campaign local --preset smoke --workers 2
python -m gapslice.revision.campaign worker --manifest ABSOLUTE_PATH
python -m gapslice.revision.campaign report --manifest ABSOLUTE_PATH
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
import tempfile
import time
import traceback


ROOT = Path(__file__).resolve().parents[2]
# An inherited setting from a different checkout must not redirect the inputs
# away from the files whose hashes identify this campaign.
os.environ['GAPSLICE_ROOT'] = str(ROOT)
os.environ['GAPSLICE_RESULTS'] = str(ROOT/'results')
os.environ['GAPSLICE_OUTPUT'] = str(ROOT/'outputs/legacy-generated')
THREAD_ENV = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')
for _name in THREAD_ENV:
    os.environ[_name] = '1'


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if hasattr(x, 'item'):
        return jsonable(x.item())
    if isinstance(x, float):
        import math
        return x if math.isfinite(x) else None
    return x


def canonical(x):
    return json.dumps(jsonable(x), sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.partial-', delete=False) as f:
        temp = Path(f.name)
        json.dump(jsonable(value), f, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def fingerprint(root):
    files = sorted((root/'gapslice').rglob('*.py'))
    files += [root/'requirements-hpc.txt']
    files += [root/'results'/name for name in ['gain_curves.npz', 'tail_table.npz']]
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    versions = {p: importlib.metadata.version(p) for p in ['numpy', 'scipy', 'cvxpy', 'clarabel', 'matplotlib']}
    return dict(files=hashes, versions=versions, python=platform.python_version())


def configurations(preset):
    full = preset == 'full'
    records = []

    def add(family, factors):
        names = list(factors)
        for values in itertools.product(*(factors[n] for n in names)):
            records.append(dict(family=family, **dict(zip(names, values))))

    add('radio', dict(h=[.6, .8, 1., 1.2, 1.5, 2.] if full else [.6, 1., 1.5], beta=[0., 2., 4.],
                      eta=[.3, .4] if full else [.3], n_trucks=[3, 5, 7] if full else [5],
                      blocked=[False, True], payload=[300, 600, 1200], rice=[0., 3., 10.], cap=[51, 106]))
    add('fading', dict(h=[.6, .8, 1., 1.2, 1.5, 2.] if full else [.6, 1.],
                       b=[20, 40, 80], rice=[0., 3., 10.], rho=[0., .5, .9, 1.],
                       seed=list(range(7000, 7010 if full else 7004)), replicates=[100000 if full else 20000]))
    add('control', dict(h=[.6, .8, 1., 1.2, 1.5] if full else [.6, 1., 1.5], beta=[0., 2., 4.],
                        eta=[.3, .4] if full else [.3], n_trucks=[3, 5, 7, 10, 20] if full else [3, 5, 7],
                        rho=[0., .5, .9], delivery_margin=[0., -.05], brake=['moderate', 'hard'],
                        seed=list(range(7000, 7010 if full else 7004)), replicates=[1000 if full else 200]))
    add('market', dict(tenants=[4, 8, 20, 40, 80, 160, 320] if full else [4, 20, 40, 80],
                       pool=[3000., 6000., 12000.], contract=['A', 'B'],
                       seed=list(range(7000, 7030 if full else 7004))))
    if preset == 'smoke':
        small = []
        for family in ['radio', 'fading', 'control', 'market']:
            c = next(r for r in records if r['family'] == family).copy()
            if 'replicates' in c:
                c['replicates'] = 64 if family == 'control' else 500
            small.append(c)
        records = small
    random.Random(935).shuffle(records)
    return records


def build(root, preset):
    configs = configurations(preset)
    header = dict(schema=1, stage='synthetic_diagnostic', preset=preset,
                  fingerprint=fingerprint(root), configs=configs)
    campaign_id = f'ojcs-{preset}-{sha(header)[:16]}'
    tasks = [dict(id=sha(c)[:20], config=c) for c in configs]
    if len({t['id'] for t in tasks}) != len(tasks):
        raise AssertionError('Duplicate task configs/identifiers')
    manifest = dict(**header, campaign_id=campaign_id, tasks=tasks)
    path = root/'outputs/ojcs/manifests'/f'{campaign_id}.json'
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise RuntimeError('Existing manifest differs; refusing overwrite')
    else:
        atomic_json(path, manifest)
    return path


def read_manifest(root, path):
    root = root.resolve()
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError('Manifest must be inside this project')
    m = json.loads(path.read_text())
    header = {k: m[k] for k in ['schema', 'stage', 'preset', 'fingerprint', 'configs']}
    expected_id = f'ojcs-{m["preset"]}-{sha(header)[:16]}'
    if m['campaign_id'] != expected_id or m['configs'] != [t['config'] for t in m['tasks']]:
        raise ValueError('Manifest identity/configuration mismatch')
    if any(t['id'] != sha(t['config'])[:20] for t in m['tasks']):
        raise ValueError('Task identity mismatch')
    if m['fingerprint'] != fingerprint(root):
        raise RuntimeError('Code, dependency versions or input tables changed: build a new manifest')
    if Path(m['campaign_id']).name != m['campaign_id']:
        raise ValueError('Invalid campaign identifier')
    return m


def locations(root, m):
    base = root/'outputs/ojcs'/m['campaign_id']
    return base, base/'results', root/'logs'/m['campaign_id']


def attempt_id():
    value = os.environ.get('GS_OJCS_ATTEMPT', os.environ.get('SLURM_JOB_ID', 'local'))
    if not value or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in value):
        raise ValueError('Invalid execution attempt identifier')
    return value


def worker(root, path, rank, world):
    from gapslice.revision.experiments import DISPATCH
    m = read_manifest(root, path)
    base, result_dir, log_dir = locations(root, m)
    attempt = attempt_id()
    log_dir = log_dir/attempt
    worker_dir = base/'workers'/attempt
    for d in [result_dir, log_dir, worker_dir]:
        d.mkdir(parents=True, exist_ok=True)
    failed = completed = skipped = 0
    shard = m['tasks'][rank::world]
    log_path = log_dir/f'progress-{rank:03d}.log'
    with log_path.open('a', buffering=1) as log:
        for number, task in enumerate(shard, 1):
            key = task['id']
            out = result_dir/f'{key}.json'
            if out.exists():
                previous = json.loads(out.read_text())
                if previous.get('campaign_id') != m['campaign_id'] or previous.get('config') != task['config']:
                    raise RuntimeError('Existing result identity mismatch; refusing overwrite')
                if previous.get('status') == 'complete':
                    skipped += 1
                    continue
                raise RuntimeError('Unexpected existing incomplete result')
            start = time.perf_counter()
            cpu_start = time.process_time()
            try:
                c = task['config']
                result = DISPATCH[c['family']](c)
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                rss_mb = rss/(1024**2 if sys.platform == 'darwin' else 1024)
                atomic_json(out, dict(campaign_id=m['campaign_id'], id=key, config=c, status='complete',
                                      stage='synthetic_diagnostic', metrics=result, rank=rank,
                                      wall_s=time.perf_counter()-start, cpu_s=time.process_time()-cpu_start,
                                      process_peak_rss_mb=rss_mb, hostname=platform.node()))
                failure_path = result_dir/f'{key}.failed.json'
                if failure_path.exists():
                    failure_path.unlink()
                completed += 1
                line = f'COMPLETE rank={rank} progress={number}/{len(shard)} family={c["family"]} task={key}'
            except Exception:
                failed += 1
                detail = traceback.format_exc()
                atomic_json(result_dir/f'{key}.failed.json', dict(id=key, config=task['config'],
                                                                 campaign_id=m['campaign_id'], status='failed', traceback=detail))
                line = f'FAILED rank={rank} progress={number}/{len(shard)} task={key}\n{detail}'
            print(line, flush=True)
            print(line, file=log)
    atomic_json(worker_dir/f'{rank:03d}.json',
                dict(attempt=attempt, rank=rank, world=world, assigned=len(shard), completed=completed, skipped=skipped, failed=failed))
    return 1 if failed else 0


def flatten(value, prefix=''):
    result = {}
    for k, v in value.items():
        key = f'{prefix}{k}'
        if isinstance(v, dict):
            result.update(flatten(v, key+'.'))
        else:
            result[key] = canonical(v) if isinstance(v, list) else v
    return result


def report(root, path, allow_incomplete=False):
    m = read_manifest(root, path)
    base, result_dir, log_dir = locations(root, m)
    good, failures, pending = [], [], []
    families = {}
    for task in m['tasks']:
        family = task['config']['family']
        count = families.setdefault(family, dict(expected=0, complete=0, failed=0, pending=0))
        count['expected'] += 1
        p = result_dir/f'{task["id"]}.json'
        fail = result_dir/f'{task["id"]}.failed.json'
        if p.exists():
            value = json.loads(p.read_text())
            if value.get('campaign_id') != m['campaign_id'] or value.get('config') != task['config'] or value.get('status') != 'complete':
                raise RuntimeError(f'Invalid result identity/status: {p}')
            good.append(value); count['complete'] += 1
        elif fail.exists():
            failures.append(str(fail)); count['failed'] += 1
        else:
            pending.append(task['id']); count['pending'] += 1
    attempt = attempt_id()
    worker_records = list((base/'workers'/attempt).glob('*.json')) if (base/'workers'/attempt).is_dir() else []
    summary = dict(campaign_id=m['campaign_id'], stage=m['stage'], preset=m['preset'],
                   expected=len(m['tasks']), complete=len(good), failed=len(failures), pending=len(pending),
                   attempt=attempt, worker_records=len(worker_records), families=families, failed_logs=failures,
                   result_dir=str(result_dir), progress_log_dir=str(log_dir/attempt),
                   diagnostic_cpu_s=sum(r['cpu_s'] for r in good),
                   maximum_observed_process_rss_mb=max((r['process_peak_rss_mb'] for r in good), default=0.),
                   generated_utc=datetime.now(timezone.utc).isoformat(),
                   limitations='Entirely synthetic diagnostics using inherited models. No new stability/safety/privacy guarantee, final method evaluation or measured-data validation.')
    atomic_json(base/'summary.json', summary)
    flat = [flatten(r) for r in good]
    fields = sorted({key for row in flat for key in row})
    if fields:
        with (base/'metrics.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader(); writer.writerows(flat)
    lines = ['# OJ-CS diagnostic campaign', '',
             'These are synthetic diagnostic runs, not final results for a revised manuscript.', '',
             f'Campaign: `{m["campaign_id"]}`', '',
             '| Family | Expected | Complete | Failed | Pending |', '|---|---:|---:|---:|---:|']
    for family, counts in sorted(families.items()):
        lines.append('| '+family+' | '+' | '.join(str(counts[k]) for k in ['expected','complete','failed','pending'])+' |')
    lines += ['', f'Worker records: {len(worker_records)}. CPU seconds measured inside completed tasks: {summary["diagnostic_cpu_s"]:.2f}.',
              '', 'Code, environment versions and input hashes are recorded in the manifest.',
              'A completed task may report an unavailable descriptor or infeasible radio target; those are scientific outcomes, not execution failures.',
              'Finite sample event intervals are pointwise; cross-scenario claims need the planned cluster-level statistical analysis.',
              '', 'Remaining work: explicit NR transport blocks/overheads, coupled scheduling and interference, latency-aware control, whole-maneuver guarantees, new-method evaluation and independent validation.',
              '', f'Raw records: `{result_dir}`', f'Metrics: `{base / "metrics.csv"}`',
              f'Failures: `{result_dir}/*.failed.json`', f'Progress: `{log_dir / attempt}`', '']
    (base/'report.md').write_text('\n'.join(lines))
    print(json.dumps(summary, indent=2))
    return 0 if allow_incomplete or not failures and not pending else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['build', 'local']:
        p = sub.add_parser(name)
        p.add_argument('--preset', choices=['smoke', 'audit', 'full'], default='audit')
        if name == 'local':
            p.add_argument('--workers', type=int, default=2)
    p = sub.add_parser('worker')
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--rank', type=int, default=int(os.getenv('SLURM_PROCID', '0')))
    p.add_argument('--world', type=int, default=int(os.getenv('SLURM_NTASKS', '1')))
    p = sub.add_parser('report')
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if root != ROOT:
        raise ValueError('Run from this source checkout; moving outputs outside it is unsupported')
    if args.command in ['build', 'local']:
        path = build(root, args.preset)
        if args.command == 'build':
            print(path)
            return 0
        count = min(args.workers, len(json.loads(path.read_text())['tasks']))
        if count < 1:
            raise ValueError('At least one worker required')
        os.environ['GS_OJCS_ATTEMPT'] = f'local-{time.time_ns()}'
        log_dir = root/'logs/local'/attempt_id()
        log_dir.mkdir(parents=True, exist_ok=True)
        children, handles = [], []
        try:
            for rank in range(count):
                handle = (log_dir/f'worker-{rank:03d}.log').open('a')
                handles.append(handle)
                command = [sys.executable, '-m', 'gapslice.revision.campaign', 'worker',
                           '--manifest', str(path), '--rank', str(rank), '--world', str(count)]
                children.append(subprocess.Popen(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT))
            codes = [p.wait() for p in children]
        finally:
            for handle in handles:
                handle.close()
        rc = report(root, path)
        return 1 if any(codes) or rc else 0
    if args.command == 'worker':
        if args.world < 1 or not 0 <= args.rank < args.world:
            raise ValueError('Invalid rank/world')
        return worker(root, args.manifest, args.rank, args.world)
    return report(root, args.manifest, args.allow_incomplete)


if __name__ == '__main__':
    raise SystemExit(main())
