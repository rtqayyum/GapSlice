#!/usr/bin/env python3
"""Read-only progress and sampled fresh-work ETA; never imports the simulator.

Counts are deduplicated COMPLETE/RESUME log records, not a raw-data integrity
audit. No project files, Slurm jobs or environments are changed. The ETA covers
remaining calibration/test shards only; it excludes diagnostics and reporting.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import time


STAGES = ('design', 'calibration', 'test')


def command(args):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=25)
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        return '', str(error), 1


def accounting(job):
    queue, error, code = command(['squeue', '-h', '-j', job, '-o', '%T|%C|%M|%L|%R'])
    if queue:
        print('LIVE state|CPUs|elapsed|time left|nodes/reason: ' + queue, flush=True)
    elif code:
        print('Live queue unavailable: ' + error, flush=True)
    rows, error, code = command(['sacct', '-n', '-P', '-j', job,
                                 '--format=JobIDRaw,State,ExitCode,Elapsed,AllocCPUS,MaxRSS,NodeList%60'])
    print('ACCOUNTING job/step|state|exit code|elapsed|CPUs|MaxRSS|nodes:\n' + (rows or error or '(not available)'), flush=True)
    state = queue.split('|')[0].strip() if queue else None
    if state is None and not code:
        for line in rows.splitlines():
            fields = line.split('|')
            if fields[0].strip() == job:
                state = fields[1].strip().split()[0].rstrip('+')
    return state


def expected(study):
    result = {}
    for stage in STAGES:
        path = study / stage / 'summary.json'
        if path.is_file():
            result[stage] = json.loads(path.read_text())['expected']
    selection = study / 'selection.json'
    if selection.is_file():
        # Protocol precedes the large candidate bank in the immutable study.
        with (study / 'study.json').open() as stream:
            prefix = stream.read(65536)
        match = re.search(r'"protocol"\s*:\s*', prefix)
        if match is None:
            raise ValueError('Cannot read frozen protocol prefix')
        protocol, _ = json.JSONDecoder().raw_decode(prefix[match.end():])
        candidates = len(json.loads(selection.read_text())['selected'])
        for stage in ('calibration', 'test'):
            n, batch = protocol[f'{stage}_n'], protocol['batch']
            if n % min(n, batch):
                raise ValueError('Unexpected shard geometry')
            total = candidates * len(protocol['environments']) * (n // min(n, batch))
            if stage in result and result[stage] != total:
                raise ValueError('Stage summary and frozen protocol disagree')
            result[stage] = total
    return result


def snapshot(project, study, job):
    values = {stage: dict(done=set(), fresh=set(), reused=set(), failed=set()) for stage in STAGES}
    directory = project / 'logs' / study.name
    for attempt in sorted(directory.glob('*')):
        if not attempt.is_dir():
            continue
        for stage in STAGES:
            row = values[stage]
            for path in (attempt / stage).glob('progress-*.log'):
                with path.open() as stream:
                    for line in stream:
                        if not line.endswith('\n'):
                            continue  # A worker can still be appending the final line.
                        parts = line.split()
                        if not parts or parts[0] not in {'COMPLETE', 'RESUME', 'FAILED'}:
                            continue
                        fields = dict(p.split('=', 1) for p in parts[1:] if '=' in p)
                        task = fields.get('task', '')
                        if not re.fullmatch('[0-9a-f]{24}', task):
                            continue
                        if parts[0] in {'COMPLETE', 'RESUME'}:
                            row['done'].add(task)
                        if attempt.name == job:
                            key = {'COMPLETE': 'fresh', 'RESUME': 'reused', 'FAILED': 'failed'}[parts[0]]
                            row[key].add(task)
    return dict(stages=values, sampled_at=time.monotonic())


def show(snap, totals):
    print('Snapshot UTC: ' + datetime.now(timezone.utc).isoformat(), flush=True)
    for stage, row in snap['stages'].items():
        done, total = len(row['done']), totals.get(stage)
        fraction = f'{done:,}/{total:,} ({100 * done / total:.1f}%)' if total else f'{done:,}/unknown'
        print(f'{stage}: logged complete {fraction}; this job fresh={len(row["fresh"]):,}, '
              f'reused={len(row["reused"]):,}, failed events={len(row["failed"]):,}', flush=True)


def estimate(before, after, totals, state):
    stages = ('calibration', 'test')
    if state != 'RUNNING':
        return f'ETA unavailable: current job state is {state or "unconfirmed"}.'
    if any(stage not in totals for stage in stages):
        return 'ETA unavailable: complete frozen calibration/test totals are not available.'
    if any(after['stages'][s]['failed'] - after['stages'][s]['fresh'] - after['stages'][s]['reused'] for s in STAGES):
        return 'ETA unavailable: this attempt has unresolved failed task events.'
    remaining = sum(max(0, totals[s] - len(after['stages'][s]['done'])) for s in stages)
    if not remaining:
        return 'Main calibration/test replays are logged complete; verification, diagnostics or reporting may remain.'
    if any(not before['stages'][s]['fresh'] <= after['stages'][s]['fresh'] for s in stages):
        return 'ETA unavailable: progress logs changed or disappeared during sampling.'
    elapsed = after['sampled_at'] - before['sampled_at']
    fresh = sum(len(after['stages'][s]['fresh'] - before['stages'][s]['fresh']) for s in stages)
    if elapsed < 30 or fresh < 10:
        return f'ETA unavailable: only {fresh} fresh main shards in {elapsed:.0f}s; sample again after workers make more progress.'
    rate = fresh / elapsed
    hours = remaining / rate / 3600
    finish = datetime.now(timezone(timedelta(hours=4))) + timedelta(hours=hours)
    return (f'FRESH throughput: {fresh:,} shards / {elapsed:.0f}s = {rate * 3600:,.0f} shards/hour.\n'
            f'Remaining main shards: {remaining:,}. Rough calibration + test ETA: {hours:.1f} hours ({hours / 24:.1f} days).\n'
            f'Projected main-replay finish (Dubai): {finish:%Y-%m-%d %H:%M}.\n'
            'Short-window extrapolation assumes similar future throughput and resources; stragglers can extend it.\n'
            'Diagnostics, data verification, allocation and reporting add time. This is not a full-job completion promise.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--job', required=True)
    parser.add_argument('--sample', type=int, default=60, help='Seconds between read-only samples; 0 skips ETA; 300 gives a longer window')
    a = parser.parse_args()
    if not a.job.isdigit() or not 0 <= a.sample <= 3600:
        parser.error('Numeric job ID and sample interval from 0 to 3600 required')
    project = a.project.resolve()
    state = accounting(a.job)
    study = Path((project / f'outputs/cert/jobs/{a.job}.study').read_text().strip()).resolve()
    if not study.is_relative_to(project / 'outputs/cert/studies'):
        raise ValueError('Study mapping is outside this project')
    print('Study: ' + str(study), flush=True)
    for label, path in [('BATCH', project / f'outputs/job-{a.job}/status.json'),
                         ('PROBE', study / f'runtime/{a.job}/probe.json'),
                         ('FAILURE', study / f'runtime/{a.job}/failure.json')]:
        if path.is_file():
            print(f'{label}: {path.read_text().strip()}', flush=True)
    for suffix in ('out', 'err'):
        path = project / f'logs/gs_cert_research_{a.job}.{suffix}'
        if path.is_file():
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 16384))
                print(f'MAIN .{suffix} (last 12 lines):\n' + '\n'.join(stream.read().decode(errors='replace').splitlines()[-12:]), flush=True)
        else:
            print(f'MAIN .{suffix}: not created', flush=True)
    totals = expected(study)
    first = snapshot(project, study, a.job)
    show(first, totals)
    if state != 'RUNNING' or not a.sample:
        print('No active sampling; running state and fresh completions are required for an ETA.', flush=True)
        return
    print(f'Sampling fresh completions for {a.sample} seconds; no files or jobs are changed.', flush=True)
    time.sleep(a.sample)
    second = snapshot(project, study, a.job)
    show(second, totals)
    state = accounting(a.job)
    print(estimate(first, second, totals, state), flush=True)


if __name__ == '__main__':
    main()
