#!/usr/bin/env python3
"""Recorded operational adapter for an existing, frozen certified study.

Only scheduling, optional worker telemetry and ordered result prefetch change.
Scientific tasks, RNG streams, commit validation and aggregation arithmetic use
the original campaign. This adapter has its OWN hash/provenance, in addition to
the frozen base fingerprint; its generated Batch never replaces the base file.
"""
import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time
import uuid


VERSION = 2
DEFAULT_PROJECT = Path('/home/tariq.qayyum/hpc/GapSlice-OJCS')
DISPATCH = '"$PY" -m gapslice.certified.campaign run --preset "$PRESET" --workers "$SLURM_NTASKS"'


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    """Required operational records fail closed, just like scientific commits."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.runtime-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex}')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def campaign(project):
    sys.path.insert(0, str(project))
    from gapslice.certified import campaign as c
    if c.ROOT.resolve() != Path(project).resolve():
        raise RuntimeError('Imported a different project checkout')
    return c


def helper(project):
    sys.path.insert(0, str(Path(project) / 'scripts'))
    import scale_certified
    return scale_certified


def geometry(cpus, per_node):
    if cpus < 1 or per_node < 1 or cpus % per_node:
        raise ValueError('CPUs must be a positive multiple of tasks-per-node')
    return cpus // per_node


def cpu_budget(qos_text, running_text, cpus):
    """Read the EFFECTIVE selected QoS, never a presumed 1,600-CPU allowance."""
    records = [line.split('|') for line in qos_text.splitlines() if line.split('|')[0] == 'limit']
    if len(records) != 1:
        raise RuntimeError('Cannot determine limit QoS CPU allowance')
    tres = dict(x.split('=', 1) for x in records[0][1].split(',') if '=' in x)
    if not tres.get('cpu', '').isdigit():
        raise RuntimeError('QoS has no readable finite per-user CPU limit')
    limit = int(tres['cpu'])
    used = sum(int(line.strip()) for line in running_text.splitlines() if line.strip())
    if used + cpus > limit:
        raise RuntimeError(f'Request would use {used + cpus}/{limit} CPUs; no job submitted')
    return used, limit


def batch_text(original, runner, spec_path):
    if original.count(DISPATCH) != 1:
        raise RuntimeError('Base Batch dispatch changed; refusing to generate a replacement')
    dispatch = f'"$PY" {shlex.quote(str(runner))} run --spec {shlex.quote(str(spec_path))} --workers "$SLURM_NTASKS"'
    return original.replace(DISPATCH, dispatch)


def load_spec(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text())
    project = Path(spec['project']).resolve()
    if not path.is_relative_to(project / 'outputs/cert/runtime'):
        raise RuntimeError('Runtime spec must be inside this project')
    if (spec['version'] != VERSION or digest(__file__) != spec['adapter_sha256']
            or digest(spec['batch']) != spec['batch_sha256']):
        raise RuntimeError('Runtime adapter or effective Batch hash mismatch')
    if geometry(spec['cpus'], spec['per_node']) != spec['nodes']:
        raise RuntimeError('Invalid recorded worker geometry')
    if spec.get('probe_slow_delay_s', 0) <= 30:
        raise RuntimeError('Uneven-completion probe must exceed the former 30-second cutoff')
    return spec


def submit(project, old, cpus=768, per_node=64, exclude=''):
    """Resume ONLY after the explicitly named old job is confirmed terminated."""
    project = Path(project).resolve()
    old = str(old)
    nodes = geometry(cpus, per_node)
    if project != DEFAULT_PROJECT.resolve() or not old.isdigit():
        raise ValueError('Use the existing HPC project and a numeric source job')
    h = helper(project)
    study_id = h.verify_study(project, old)
    if not h.old_job_ended(old):
        raise RuntimeError('Old job is still active or termination unconfirmed; nothing submitted')
    owner = h.guard_owner(project)
    if owner not in {None, old}:
        raise RuntimeError(f'Project guard belongs to {owner}, not {old}; nothing submitted')
    # Confirm accounting owner/name as well as the project-local immutable mapping.
    accounting = h.command(['sacct', '-X', '-n', '-P', '-j', old,
                            '--format=JobIDRaw,User%64,JobName%64'])
    expected_owner = [[x.strip() for x in line.split('|')[:3]] for line in accounting.splitlines()
                      if line.split('|')[0].strip() == old]
    if expected_owner != [[old, getpass.getuser(), 'gs_cert_research']]:
        raise RuntimeError('Source job accounting identity does not match this user/project')
    qos = h.command(['sacctmgr', '-n', '-P', 'show', 'qos', 'where', 'name=limit',
                     'format=Name,MaxTRESPerUser%120'])
    running = h.command(['squeue', '-h', '--array', '-u', getpass.getuser(),
                         '-t', 'RUNNING,COMPLETING,SUSPENDED', '-o', '%C'])
    used, limit = cpu_budget(qos, running, cpus)
    fields = dict(x.split('=', 1) for x in h.command(
        ['scontrol', 'show', 'partition', 'longq', '-o']).split() if '=' in x)
    rtime = fields.get('MaxTime')
    if not rtime or rtime in {'INFINITE', 'UNLIMITED'}:
        raise RuntimeError('Cannot read a finite longq maximum runtime')
    c = campaign(project)
    study = Path((project / f'outputs/cert/jobs/{old}.study').read_text().strip()).resolve()
    control = project / 'outputs/cert/runtime' / f'{old}-{time.time_ns()}'
    control.mkdir(parents=True)
    runner, batch, spec_path = control / 'adapter.py', control / 'Batch', control / 'spec.json'
    runner.write_bytes(Path(__file__).read_bytes())
    batch.write_text(batch_text((project / 'Batch').read_text(), runner, spec_path))
    spec = dict(version=VERSION, project=str(project), study=str(study), study_id=study_id,
                from_job=old, cpus=cpus, nodes=nodes, per_node=per_node, exclude=exclude,
                partition='longq', qos='limit', time_limit=rtime, memory_per_cpu='4G',
                adapter=str(runner), adapter_sha256=digest(runner), batch=str(batch),
                batch_sha256=digest(batch), base_batch_sha256=digest(project / 'Batch'),
                base_source=c.source(), created_utc=utc(), cpu_usage_at_submission=used,
                qos_cpu_limit=limit, metadata_prefetch_threads=8, probe_slow_delay_s=40,
                changes=['compact placement', 'full geometry I/O probe',
                         'optional heartbeat retries', 'fail fast on srun error',
                         'unlimited successful-peer wait; 40-second uneven completion probe',
                         'ordered hash-validated result prefetch; unchanged arithmetic'])
    write_json(spec_path, spec)
    subprocess.run(['bash', '-n', str(batch)], check=True)
    args = ['--job-name=gs_cert_research', '--partition=longq', '--qos=limit',
            f'--nodes={nodes}', f'--ntasks={cpus}', f'--ntasks-per-node={per_node}',
            '--distribution=block:block', '--cpus-per-task=1', '--mem-per-cpu=4G',
            f'--time={rtime}', f'--chdir={project}',
            '--export=ALL,GS_OJCS_STAGE=certified,GS_OJCS_PRESET=research']
    if exclude:
        args.append(f'--exclude={exclude}')
    print(f'Frozen study: {study_id}\nRequest: {nodes} nodes x {per_node} ranks = {cpus} CPUs; '
          f'user total {used + cpus}/{limit}; {rtime}; no GPU\nRuntime provenance: {spec_path}', flush=True)
    h.command(['sbatch', '--test-only', *args, str(batch)])
    job = h.command(['sbatch', '--parsable', '--hold', *args, str(batch)]).split(';', 1)[0]
    if not job.isdigit():
        raise RuntimeError(f'Unexpected sbatch reply: {job!r}; inspect queue before retrying')
    print(f'Accepted HELD job {job}; recording its receipt before guard recovery/release.', flush=True)
    receipt = project / f'outputs/cert/submissions/scale-{old}-to-{job}.json'
    value = dict(old_job=old, replacement_job=job, study=study_id, cpus=cpus,
                 projected_user_cpus=used + cpus, runtime_spec=str(spec_path), created_utc=utc())
    write_json(receipt, value)
    # Record mapping even if the full-geometry probe fails before campaign.run.
    (project / f'outputs/cert/jobs/{job}.study').write_text(str(study) + '\n')
    write_json(control / 'submission.json', dict(job=job, receipt=str(receipt), **value))
    print(f'New job {job} HELD; receipt: {receipt}', flush=True)
    try:
        h.recover(project, old, job)
    except Exception:
        print(f'Job {job} remains HELD. After resolving the reported condition, recover with:\n'
              f'{sys.executable} {project}/scripts/scale_certified.py --from-job {old} '
              f'--replacement-job {job}', file=sys.stderr, flush=True)
        raise
    print(f'Logs: {project}/logs/gs_cert_research_{job}.out / .err\n'
          f'First step: launch/I/O probe; any failure exits before simulation.\n'
          f'Report: {study}/report.md', flush=True)
    return job


def optional_heartbeat(writer, path, value, retries=3, pause=time.sleep):
    """Only telemetry is optional. The caller routes every scientific write out."""
    last = None
    for attempt in range(retries):
        try:
            writer(path, value)
            return True
        except OSError as error:
            last = error
            # NFS may report a replayed rename as missing after it committed.
            try:
                if json.loads(Path(path).read_text()) == value:
                    return True
            except (OSError, ValueError):
                pass
            if attempt + 1 < retries:
                pause(.2 * (attempt + 1))
    print(f'WARNING optional heartbeat not committed after {retries} attempts: {path}: {last}; '
          'scientific result validation remains required', file=sys.stderr, flush=True)
    return False


@contextmanager
def telemetry_adapter(c, manifest_path, attempt):
    original = c.atomic_json
    directory = Path(manifest_path).resolve().parent / 'workers' / attempt

    def routed(path, value):
        path = Path(path)
        if path.resolve().parent == directory:
            return optional_heartbeat(original, path, value)
        return original(path, value)

    c.atomic_json = routed
    try:
        yield
    finally:
        c.atomic_json = original


def worker(c, manifest_path, table_path, rank, size):
    with telemetry_adapter(c, manifest_path, os.environ.get('GS_OJCS_ATTEMPT', 'local')):
        return c.worker(manifest_path, table_path, rank, size)


def ordered_results(reader, path, items, threads=8):
    """Bound memory; preserve manifest order AND use the original validator."""
    with ThreadPoolExecutor(max_workers=threads) as pool:
        pending = deque()
        iterator = iter(items)
        for item in iterator:
            pending.append((item, pool.submit(reader, path, item)))
            if len(pending) >= 2 * threads:
                first, future = pending.popleft()
                yield first, future.result()
        while pending:
            first, future = pending.popleft()
            yield first, future.result()


def ordered_aggregate(c, original, path, threads=8):
    """Prefetch I/O only; original aggregate performs every addition in order."""
    reader, manifest_reader = c.result, c.read_manifest
    records, total, name = None, 0, ''
    done = 0

    def prepare(request_path):
        nonlocal records, total, name
        if Path(request_path) != Path(path) or records is not None:
            raise RuntimeError('Unexpected aggregation manifest access')
        m = manifest_reader(request_path)
        records = ordered_results(reader, path, m['tasks'], threads)
        total, name = len(m['tasks']), m['name']
        return m

    def consume(request_path, item, verify=True):
        nonlocal done
        expected, value = next(records)
        if Path(request_path) != Path(path) or item != expected or not verify:
            raise RuntimeError('Aggregation access order changed; refusing an altered reduction')
        done += 1
        if done % 5000 == 0 or done == total:
            print(f'REVALIDATE stage={name} records={done}/{total}', flush=True)
        return value

    c.result, c.read_manifest = consume, prepare
    try:
        cells = original(path)
        if done != total:
            raise RuntimeError('Aggregation did not consume all required results')
        return cells
    finally:
        c.result, c.read_manifest = reader, manifest_reader
        if records is not None:
            records.close()


def step_args(spec, log, name, timeout=None):
    args = ['srun', f'--nodes={spec["nodes"]}', f'--ntasks={spec["cpus"]}',
            f'--ntasks-per-node={spec["per_node"]}', '--distribution=block:block',
            # --wait starts after ANY first task exit, including success.
            # Independent workers must be allowed to finish at different times.
            # Zero overrides cluster WaitTime/environment defaults. Genuine
            # failures still stop the step via --kill-on-bad-exit=1.
            '--cpus-per-task=1', '--kill-on-bad-exit=1', '--wait=0',
            f'--output={log}/{name}_%t.out', f'--error={log}/{name}_%t.err']
    if timeout:
        args.append(f'--time={timeout}')
    return args


def probe_delay(spec, rank):
    # Rank zero finishes promptly. One rank per host remains alive longer
    # than the former 30-second peer-exit cutoff, before committing its record.
    return spec['probe_slow_delay_s'] if rank and (rank + 1) % spec['per_node'] == 0 else 0


def probe(spec, directory):
    """Use science geometry/I/O and exercise uneven successful rank completion."""
    rank, size = int(os.environ['SLURM_PROCID']), int(os.environ['SLURM_NTASKS'])
    if size != spec['cpus'] or not 0 <= rank < size:
        raise RuntimeError('Probe rank/count mismatch')
    delay = probe_delay(spec, rank)
    started = time.monotonic()
    if delay:
        time.sleep(delay)
    record = dict(rank=rank, size=size, host=socket.gethostname(), pid=os.getpid(),
                  local_rank=int(os.environ['SLURM_LOCALID']), utc=utc(),
                  planned_delay_s=delay, elapsed_delay_s=time.monotonic() - started)
    path = Path(directory) / f'{rank:04d}.json'
    write_json(path, record)
    if json.loads(path.read_text()) != record:
        raise RuntimeError('Probe write/read mismatch')
    print(json.dumps(record), flush=True)
    print(f'PROBE stderr OK rank={rank}', file=sys.stderr, flush=True)


def validate_probe(directory, spec):
    rows = [json.loads((Path(directory) / f'{rank:04d}.json').read_text())
            for rank in range(spec['cpus'])]
    if {x['rank'] for x in rows} != set(range(spec['cpus'])) or any(x['size'] != spec['cpus'] for x in rows):
        raise RuntimeError('Incomplete or duplicate probe rank coverage')
    hosts = Counter(x['host'] for x in rows)
    if len(hosts) != spec['nodes'] or any(n != spec['per_node'] for n in hosts.values()):
        raise RuntimeError(f'Allocation was not compact as requested: {dict(hosts)}')
    for host in hosts:
        if {x['local_rank'] for x in rows if x['host'] == host} != set(range(spec['per_node'])):
            raise RuntimeError('Probe local rank coverage mismatch')
    delayed = 0
    for row in rows:
        required = probe_delay(spec, row['rank'])
        if row.get('planned_delay_s') != required or row.get('elapsed_delay_s', -1) < required - .1:
            raise RuntimeError('Uneven-completion probe delay was not satisfied')
        delayed += bool(required)
    return dict(ranks=len(rows), hosts=dict(hosts), passed=True, delayed_ranks=delayed,
                required_delay_s=spec['probe_slow_delay_s'], successful_peer_wait_s=0, utc=utc())


def run_probe(spec, spec_path, runtime):
    log = runtime / 'probe'
    log.mkdir(parents=True, exist_ok=True)
    args = step_args(spec, log, 'probe', '00:05:00') + [sys.executable, spec['adapter'],
           'probe', '--spec', str(spec_path), '--directory', str(log / 'records')]
    print(f'PROBE starting {spec["cpus"]} ranks on {spec["nodes"]} nodes; '
          f'late ranks delay {spec["probe_slow_delay_s"]}s; successful-peer wait unlimited', flush=True)
    code = subprocess.run(args, check=False).returncode
    if code:
        write_json(runtime / 'failure.json', dict(phase='probe', exit_code=code, utc=utc(), command=args))
        raise RuntimeError(f'Launch/I/O probe failed (srun={code}); no scientific work started. Logs: {log}')
    result = validate_probe(log / 'records', spec)
    write_json(runtime / 'probe.json', result)
    print(f'PROBE PASSED ranks={result["ranks"]} hosts={len(result["hosts"])} '
          f'delayed_ranks={result["delayed_ranks"]} delay_s={result["required_delay_s"]}', flush=True)


def execute(c, spec, spec_path, runtime, path, tables, workers, local):
    m = c.read_manifest(path)
    summary_path = Path(path).parent / 'summary.json'
    if m['name'] in {'design', 'calibration', 'test'} and summary_path.is_file():
        prior = json.loads(summary_path.read_text())
        if (prior.get('stage') == m['name'] and prior.get('expected') == len(m['tasks'])
                and prior.get('complete') == len(m['tasks']) and prior.get('worker_exit_code') == 0
                and prior.get('failed_or_pending') == 0 and prior.get('manifest') == str(path)):
            # Original run() calls aggregate next, including test via report().
            # It revalidates EVERY JSON identity and NPZ digest before use.
            print(f'REUSE completed stage={m["name"]}; full raw-data revalidation follows; no worker relaunch', flush=True)
            write_json(runtime / f'{m["name"]}-reused.json', dict(manifest=str(path),
                       manifest_sha256=c.digest(path), prior_summary=prior, utc=utc()))
            return
    print(f'STAGE {m["name"]} tasks={len(m["tasks"])} workers={workers}', flush=True)
    if local:
        code = 0
        for rank in range(workers):
            if worker(c, path, tables, rank, workers):
                code = 1
                break
    else:
        if workers != spec['cpus']:
            raise RuntimeError('Worker count differs from recorded allocation')
        log = c.ROOT / 'logs' / m['study'] / os.environ['GS_OJCS_ATTEMPT'] / m['name']
        log.mkdir(parents=True, exist_ok=True)
        args = step_args(spec, log, 'worker') + [sys.executable, spec['adapter'], 'worker',
                '--spec', str(spec_path), '--manifest', str(path), '--tables', str(tables)]
        code = subprocess.run(args, check=False).returncode
    if code:
        write_json(runtime / 'failure.json', dict(phase=m['name'], exit_code=code,
                   manifest=str(path), utc=utc(), saved_results_preserved=True))
        raise RuntimeError(f'{m["name"]} worker step failed (exit {code}); stopped without scanning cached results')
    complete = 0
    for _, value in ordered_results(c.result, path, m['tasks'], spec['metadata_prefetch_threads']):
        complete += value is not None
    summary = dict(stage=m['name'], expected=len(m['tasks']), complete=complete,
                   failed_or_pending=len(m['tasks']) - complete, worker_exit_code=0,
                   manifest=str(path), runtime_provenance=str(runtime / 'provenance.json'))
    c.atomic_json(summary_path, summary)
    print(json.dumps(summary), flush=True)
    if complete != len(m['tasks']):
        raise RuntimeError(f'Incomplete {m["name"]}; required results missing')


def install(c, spec, spec_path, runtime):
    original_aggregate, original_execute = c.aggregate, c.execute
    c.execute = lambda path, tables, workers, local: execute(
        c, spec, spec_path, runtime, path, tables, workers, local)
    c.aggregate = lambda path: ordered_aggregate(
        c, original_aggregate, path, spec['metadata_prefetch_threads'])
    return original_aggregate, original_execute


def run(spec, spec_path, workers):
    if (workers != spec['cpus'] or int(os.environ['SLURM_NTASKS']) != workers
            or int(os.environ['SLURM_JOB_NUM_NODES']) != spec['nodes']):
        raise RuntimeError('Actual allocation differs from recorded compact request')
    c = campaign(spec['project'])
    study_path = Path(spec['study']) / 'study.json'
    frozen = c.read_study(study_path)
    if (frozen['id'] != spec['study_id'] or c.source() != spec['base_source']
            or digest(c.ROOT / 'Batch') != spec['base_batch_sha256']):
        raise RuntimeError('Base study/source changed; refusing cached result reuse')
    del frozen  # Do not retain an extra large candidate bank in the coordinator.
    job = os.environ['SLURM_JOB_ID']
    runtime = Path(spec['study']) / 'runtime' / job
    runtime.mkdir(parents=True, exist_ok=True)
    provenance = dict(spec=spec, spec_path=str(spec_path), spec_sha256=digest(spec_path),
                      job=job, started_utc=utc(), status='starting',
                      slurm_version=subprocess.run(['srun', '--version'], check=True, text=True,
                                                   capture_output=True).stdout.strip())
    write_json(runtime / 'provenance.json', provenance)
    try:
        run_probe(spec, spec_path, runtime)
        # All original science/selection/qualification/report functions remain.
        original_aggregate, original_execute = install(c, spec, spec_path, runtime)
        original_make_study = c.make_study

        def checked_study(preset):
            path, value = original_make_study(preset)
            if path.resolve() != study_path.resolve() or value['id'] != spec['study_id']:
                raise RuntimeError('Original study builder did not resolve to the frozen study')
            return path, value

        c.make_study = checked_study
        try:
            c.run('research', workers, False)
        finally:
            c.aggregate, c.execute = original_aggregate, original_execute
            c.make_study = original_make_study
        provenance.update(status='completed', finished_utc=utc())
        write_json(runtime / 'provenance.json', provenance)
        # Small companion bundle preserves the changed execution provenance.
        import tarfile
        with tarfile.open(runtime / 'runtime_bundle.tar.gz', 'w:gz') as archive:
            for path, name in [(Path(spec['adapter']), 'adapter.py'), (Path(spec['batch']), 'Batch'),
                               (Path(spec_path), 'spec.json'), (runtime / 'provenance.json', 'provenance.json'),
                               (runtime / 'probe.json', 'probe.json')]:
                archive.add(path, arcname=name, recursive=False)
        print(f'RUNTIME PROVENANCE {runtime}/runtime_bundle.tar.gz', flush=True)
    except Exception as error:
        provenance.update(status='failed', finished_utc=utc(), error=str(error))
        write_json(runtime / 'provenance.json', provenance)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('submit')
    p.add_argument('--project', type=Path, default=DEFAULT_PROJECT)
    p.add_argument('--from-job', required=True)
    p.add_argument('--cpus', type=int, default=768)
    p.add_argument('--per-node', type=int, default=64)
    p.add_argument('--exclude', default='', help='Explicit optional node exclusion; no node is blamed automatically')
    for name in ['run', 'worker', 'probe']:
        p = sub.add_parser(name)
        p.add_argument('--spec', type=Path, required=True)
        if name == 'run':
            p.add_argument('--workers', type=int, required=True)
        elif name == 'worker':
            p.add_argument('--manifest', type=Path, required=True)
            p.add_argument('--tables', type=Path, required=True)
        else:
            p.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'submit':
        submit(args.project, args.from_job, args.cpus, args.per_node, args.exclude)
        return 0
    spec = load_spec(args.spec)
    if args.action == 'probe':
        probe(spec, args.directory)
        return 0
    if args.action == 'run':
        run(spec, args.spec, args.workers)
        return 0
    c = campaign(spec['project'])
    if c.source() != spec['base_source']:
        raise RuntimeError('Worker base source differs from recorded provenance')
    if not args.manifest.resolve().is_relative_to(Path(spec['study']).resolve()):
        raise RuntimeError('Worker manifest is outside the recorded frozen study')
    return int(worker(c, args.manifest, args.tables, int(os.environ['SLURM_PROCID']),
                      int(os.environ['SLURM_NTASKS'])) > 0)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {getattr(error, "stderr", None) or error}', file=sys.stderr, flush=True)
        sys.exit(1)
