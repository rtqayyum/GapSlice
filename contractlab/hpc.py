"""Cluster launch, uneven completion probe and compact progress/ETA."""
import argparse
from collections import Counter
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from contractlab.common import ROOT,BASE,atomic,immutable,fingerprint,sha,utc

HPC=Path('/home/tariq.qayyum/hpc/GapSlice-OJCS')


def command(args):
    return subprocess.run(args,check=True,capture_output=True,text=True).stdout.strip()


def quota(qos,running,cpus):
    rows=[line.split('|') for line in qos.splitlines() if line.split('|')[0].strip()=='limit']
    if len(rows)!=1:raise RuntimeError('Cannot read effective limit QoS')
    fields=dict(x.split('=',1) for x in rows[0][1].strip().split(',') if '=' in x)
    if not fields.get('cpu','').isdigit():raise RuntimeError('Cannot verify finite QoS CPU allowance')
    limit=int(fields['cpu']);used=sum(int(x) for x in running.splitlines() if x.strip())
    if used+cpus>limit:raise RuntimeError(f'Request exceeds current allowance: {used}+{cpus}>{limit}; no submission')
    return used,limit


def resources(preset):
    return dict(smoke=(4,4,'shortq'),pilot=(32,32,'shortq'),research=(480,32,'longq'))[preset]


def submit(preset,resume=False):
    if ROOT.resolve()!=HPC.resolve():raise RuntimeError('Submit this command on the HPC checkout')
    cpus,pernode,queue=resources(preset)
    check(preset)
    used,limit=quota(command(['sacctmgr','-n','-P','show','qos','where','name=limit','format=Name,MaxTRESPerUser%120']),
        command(['squeue','-h','--array','-u',getpass.getuser(),'-t','RUNNING,COMPLETING,SUSPENDED','-o','%C']),cpus)
    active=command(['squeue','-h','-u',getpass.getuser(),'-o','%i|%j|%T'])
    if any('|gs_contract_' in line for line in active.splitlines()):raise RuntimeError('A contract job is already active/pending; use status rather than submitting a duplicate')
    fields=dict(x.split('=',1) for x in command(['scontrol','show','partition',queue,'-o']).split() if '=' in x)
    runtime=fields.get('MaxTime')
    if not runtime or runtime in {'INFINITE','UNLIMITED'}:raise RuntimeError('Cannot verify queue maximum time')
    guard=ROOT/'outputs/ojcs/.campaign.guard'
    if guard.exists():raise RuntimeError(f'Existing project guard needs ownership inspection before launch: {guard}')
    # A research run must follow an actual pilot from the same source/runtime.
    if preset=='research':
        source=fingerprint();pilot=[p for p in (BASE/'studies').glob('contract-pilot-*')
            if (p/'status.json').is_file() and json.loads((p/'status.json').read_text()).get('state')=='COMPLETED'
            and json.loads((p/'protocol.json').read_text())['source']==source]
        if not pilot:raise RuntimeError('Run and complete the pilot with this exact code first; research not submitted')
        # The pilot is an infrastructure and throughput gate, not positive-result
        # selection. Zero qualifying contracts is a valid negative study outcome.
    args=['--parsable','--hold','--job-name=gs_contract_'+preset,'--partition='+queue,'--qos=limit',
          '--nodes='+str(cpus//pernode),'--ntasks='+str(cpus),'--ntasks-per-node='+str(pernode),
          '--cpus-per-task=1','--distribution=block:block','--mem-per-cpu=4G','--time='+runtime,
          '--chdir='+str(ROOT),'--exclude=cn164,cn171',
          '--export=ALL,GS_CONTRACT_PRESET='+preset]
    print(f'Request: {cpus} CPU ranks, {cpus//pernode} nodes x {pernode}, 4G/CPU; {queue} maximum {runtime}; no GPU. User total {used+cpus}/{limit}.',flush=True)
    command(['sbatch','--test-only',*[x for x in args if x not in {'--parsable','--hold'}],str(ROOT/'BatchContracts')])
    job=command(['sbatch',*args,str(ROOT/'BatchContracts')]).split(';')[0]
    if not job.isdigit():raise RuntimeError('Unexpected sbatch reply; inspect queue before retrying: '+job)
    print('Accepted HELD job '+job+'; recording receipt before release.',flush=True)
    value=dict(job=job,preset=preset,cpus=cpus,per_node=pernode,time_limit=runtime,partition=queue,
               source_sha256=sha(fingerprint()),utc=utc(),resumes_same_fingerprint=resume)
    immutable(BASE/'submissions'/f'{job}.json',value)
    command(['scontrol','release',job])
    print(f'Submitted {job}.\nMonitor: {sys.executable} -m contractlab.hpc status --job {job}',flush=True)


def recover(job):
    if ROOT.resolve()!=HPC.resolve() or not str(job).isdigit():raise RuntimeError('Recover a numeric job on the HPC checkout')
    receipt=BASE/'submissions'/f'{job}.json'
    if not receipt.is_file():raise RuntimeError('No project submission receipt for this job')
    rows=[line.split('|')[:4] for line in command(['sacct','-X','-n','-P','-j',job,
            '--format=JobIDRaw,User%64,JobName%64,State%40']).splitlines() if line.split('|')[0].strip()==job]
    if len(rows)!=1:raise RuntimeError('Cannot establish job identity/terminal state')
    jid,user,name,state=[x.strip() for x in rows[0]]
    if user!=getpass.getuser() or not name.startswith('gs_contract_') or state.split()[0] not in {'FAILED','COMPLETED','CANCELLED','TIMEOUT','NODE_FAIL','OUT_OF_MEMORY','PREEMPTED'}:
        raise RuntimeError('Job is active or not owned by this contract project')
    live=command(['squeue','-h','--array','-u',getpass.getuser(),'-o','%i'])
    if job in live.splitlines():raise RuntimeError('Job still appears in live queue')
    guard=ROOT/'outputs/ojcs/.campaign.guard'
    if guard.exists():
        if guard.is_symlink():raise RuntimeError('Refusing symlinked guard')
        owner=dict(line.split('=',1) for line in (guard/'owner').read_text().splitlines() if '=' in line)
        if owner.get('job_id')!=job:raise RuntimeError('Guard belongs to another job; preserved')
        target=BASE/'recovered-guards'/f'{job}-{time.time_ns()}'
        target.parent.mkdir(parents=True,exist_ok=True);os.rename(guard,target)
        print('Archived confirmed terminal owner guard:',target)
    else:print('Project guard is already clear.')
    print('All scientific results remain intact. Resume with submit '+json.loads(receipt.read_text())['preset']+' --resume')


def dependencies():
    import sumolib
    from contractlab.ldpc import frame
    from contractlab.external import native_ccc
    native_ccc()
    for prbs in [10,20,40]:
        for payload in [300,600]:
            if frame(prbs,payload,20,8187,noise=False)['failed']:raise RuntimeError('LDPC roundtrip failed')
    print(command([sumolib.checkBinary('sumo'),'--version']).splitlines()[0])
    print('Native CCC/CBF and six transport-block LDPC roundtrips passed.')


def check(preset):
    import importlib.metadata
    if Path(sys.prefix).resolve()!=ROOT/'.venv-contract':raise RuntimeError('Use this project .venv-contract interpreter')
    for line in (ROOT/'requirements-contract.txt').read_text().splitlines():
        if line and not line.startswith('#'):
            name,expected=line.split('==')
            if importlib.metadata.version(name)!=expected:raise RuntimeError('Dependency version mismatch: '+line)
    for script in [ROOT/'BatchContracts',ROOT/'hpc/contracts/prepare.sh']:
        command(['bash','-n',str(script)])
    for name in ['logs','results','outputs','figures','tmp']:(ROOT/name).mkdir(exist_ok=True)
    # Worker sizing always comes from Slurm, never a stale hard-coded 768.
    cpus=resources(preset)[0]
    if os.environ.get('SLURM_NTASKS') and int(os.environ['SLURM_NTASKS'])!=cpus:
        raise RuntimeError('Allocation geometry differs from the preset')
    print('Isolated contract runtime and shell syntax verified.',flush=True)


def probe():
    rank=int(os.environ['SLURM_PROCID']);size=int(os.environ['SLURM_NTASKS']);local=int(os.environ['SLURM_LOCALID'])
    folder=BASE/'probes'/os.environ['SLURM_JOB_ID'];folder.mkdir(parents=True,exist_ok=True)
    # Delay one rank on every node beyond the old erroneous 30s peer cutoff.
    if local==0:time.sleep(40)
    atomic(folder/f'{rank:04d}.json',dict(rank=rank,size=size,host=os.uname().nodename,delayed=local==0,utc=utc()))
    if rank==0:
        deadline=time.monotonic()+180
        while len(list(folder.glob('[0-9]*.json')))<size:
            if time.monotonic()>deadline:raise RuntimeError('Missing full-geometry launch/I/O probe ranks')
            time.sleep(1)
        rows=[json.loads(p.read_text()) for p in folder.glob('[0-9]*.json')]
        if {r['rank'] for r in rows}!=set(range(size)):raise RuntimeError('Duplicate/missing ranks')
        atomic(folder/'passed.json',dict(passed=True,ranks=size,hosts=Counter(r['host'] for r in rows),delay_s=40,peer_wait_s=0,utc=utc()))


def snapshot(job):
    try:print(command(['squeue','-h','-j',job,'-o','%i|%T|%C|%M|%L|%R']))
    except subprocess.CalledProcessError:pass
    print(command(['sacct','-n','-P','-j',job,'--format=JobID,State,ExitCode,Elapsed,AllocCPUS,MaxRSS']))
    mapping=BASE/'jobs'/f'{job}.json'
    if not mapping.exists():print('Campaign not started yet; inspect launch logs.');return None
    study=Path(json.loads(mapping.read_text())['study']);result={};print('STUDY',study)
    for stage in ['phy_fit','phy_holdout','external','design','calibration','test','diagnostics','packet','allocation']:
        manifest=study/stage/'manifest.json'
        if not manifest.exists():continue
        total=len(json.loads(manifest.read_text())['tasks']);complete=len(list((study/stage/'results').glob('*.json')))
        current=[]
        for p in (study/stage/'workers'/job).glob('*.json'):
            current.append(json.loads(p.read_text()))
        fresh=sum(r['fresh'] for r in current);reused=sum(r['reused'] for r in current)
        print(f'{stage}: committed {complete:,}/{total:,}; current fresh={fresh:,} reused={reused:,}; worker records={len(current)}')
        result[stage]=dict(complete=complete,total=total,fresh=fresh)
    if (study/'status.json').exists():print((study/'status.json').read_text())
    print('Report:',study/'report.html')
    return result


def status(job,sample):
    first=snapshot(job)
    if not first or sample<=0:return
    start=time.monotonic();time.sleep(min(sample,60));second=snapshot(job);elapsed=time.monotonic()-start
    for stage,row in (second or {}).items():
        fresh=row['fresh']-first.get(stage,{}).get('fresh',0)
        if fresh>0:
            hours=(row['total']-row['complete'])*elapsed/fresh/3600
            print(f'{stage}: {fresh} fresh tasks/{elapsed:.0f}s; rough CURRENT-STAGE ETA {hours:.1f}h. Later stages and stragglers add time; no full-job promise.')


def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('submit');p.add_argument('preset',choices=['smoke','pilot','research']);p.add_argument('--resume',action='store_true')
    p=sub.add_parser('check');p.add_argument('--preset',required=True,choices=['smoke','pilot','research'])
    sub.add_parser('dependencies');sub.add_parser('probe')
    p=sub.add_parser('status');p.add_argument('--job',required=True);p.add_argument('--sample',type=int,default=0)
    p=sub.add_parser('recover');p.add_argument('--job',required=True)
    args=parser.parse_args()
    if args.action=='submit':submit(args.preset,args.resume)
    elif args.action=='check':check(args.preset)
    elif args.action=='probe':probe()
    elif args.action=='dependencies':dependencies()
    elif args.action=='recover':recover(args.job)
    else:status(args.job,args.sample)

if __name__=='__main__':main()
