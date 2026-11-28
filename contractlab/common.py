"""Content-addressed, fail-closed artifacts for the new contract study."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/contracts'
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    os.environ[key] = '1'


def utc(): return datetime.now(timezone.utc).isoformat()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
def sha(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.partial-' + uuid.uuid4().hex)
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def immutable(path, value):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text()) != value: raise RuntimeError(f'Frozen artifact changed: {path}')
    else: atomic(path, value)
    return path


def fingerprint():
    files = [*sorted((ROOT/'contractlab').glob('*.py')),
             *sorted((ROOT/'gapslice').rglob('*.py')),
             *sorted((ROOT/'hpc/contracts').glob('*')),
             ROOT/'BatchContracts', ROOT/'requirements-contract.txt',
             ROOT/'docs/CONTRACT_FRAMEWORK.md',ROOT/'docs/CERTIFIED_PROOFS.md',
             ROOT/'hpc/environment.sh',ROOT/'hpc/project_lock.sh',
             *sorted((ROOT/'tests').glob('test_contract_*.py'))]
    if any(not p.is_file() for p in files):raise RuntimeError('A required source/launcher/proof file is missing')
    versions = {name:importlib.metadata.version(name) for name in
                ['numpy','scipy','matplotlib','py3gpp','eclipse-sumo','sumo-data','traci','sumolib']}
    return dict(files={str(p.relative_to(ROOT)):digest(p) for p in files if p.is_file()},
                versions=versions, python=platform.python_version(), system=platform.system(),
                machine=platform.machine(), base_prefix=str(Path(sys.base_prefix).resolve()))


def snapshot_sources(study,source):
    """Archive the actual source, not only its hashes, for later reproduction."""
    for name,expected in source['files'].items():
        original=ROOT/name;target=Path(study)/'source'/name
        if digest(original)!=expected:raise RuntimeError('Source changed during snapshot: '+name)
        if target.exists():
            if digest(target)!=expected:raise RuntimeError('Changed archived source: '+name)
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            temporary=target.with_name('.partial-'+uuid.uuid4().hex)
            temporary.write_bytes(original.read_bytes());os.replace(temporary,target)
        if digest(target)!=expected:raise RuntimeError('Snapshot hash mismatch: '+name)


def optional(path, value):
    for attempt in range(3):
        try: atomic(path, value); return
        except OSError:
            if attempt < 2: time.sleep(.1*(attempt+1))
    print(f'WARNING optional telemetry unavailable: {path}', file=sys.stderr, flush=True)
