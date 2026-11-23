#!/usr/bin/env python3
"""Queue a held replacement, stop one identified project job, then resume.

This standalone control-plane helper is deliberately outside the frozen
scientific/execution fingerprint. It never edits source, environments or
scientific results. Initial handovers never remove guards; explicit recovery
can archive a verified terminated owner's guard before releasing a held job.
"""
import argparse
from datetime import datetime,timezone
import getpass
import json
from pathlib import Path
import subprocess
import sys
import time


TERMINAL={'COMPLETED','CANCELLED','FAILED','TIMEOUT','OUT_OF_MEMORY','NODE_FAIL',
          'BOOT_FAIL','PREEMPTED','DEADLINE','REVOKED'}


def command(args):
    return subprocess.run(args,check=True,text=True,capture_output=True).stdout.strip()


def job_info(job):
    text=command(['scontrol','show','job',str(job),'-o'])
    return dict(field.split('=',1) for field in text.split() if '=' in field)


def verify_identity(info,job,project,user):
    if (info.get('JobId')!=str(job) or info.get('JobName')!='gs_cert_research'
            or info.get('WorkDir')!=str(project)
            or info.get('UserId','').split('(',1)[0]!=user):
        raise RuntimeError('Old job identity/owner/project does not match; no cancellation permitted')


def verify_study(project,job):
    mapping=project/'outputs/cert/jobs'/f'{job}.study'
    study=Path(mapping.read_text().strip()).resolve()
    if not study.is_relative_to(project/'outputs/cert/studies'):
        raise RuntimeError('Study mapping escapes this project')
    sys.path.insert(0,str(project))
    from gapslice.certified.campaign import ROOT,read_study
    if ROOT.resolve()!=project:raise RuntimeError('Imported a different project checkout')
    value=read_study(study/'study.json')  # verifies frozen source AND runtime
    if value['protocol']['preset']!='research':raise RuntimeError('Not a research study')
    return value['id']


def guard_owner(project):
    guard=project/'outputs/ojcs/.campaign.guard'
    if not guard.exists():return None
    owner=guard/'owner'
    if not owner.is_file():raise RuntimeError('Project guard has no readable owner; refusing handover')
    fields=dict(line.split('=',1) for line in owner.read_text().splitlines() if '=' in line)
    return fields.get('job_id','unknown')


def old_job_ended(job):
    text=command(['sacct','-X','-n','-P','-j',str(job),'--format=JobIDRaw,State%40'])
    states=[]
    for line in text.splitlines():
        fields=line.split('|')
        if len(fields)>1 and fields[0].strip()==str(job):
            states.append(fields[1].strip().split()[0].rstrip('+'))
    if len(states)!=1 or states[0] not in TERMINAL:return False
    # Accounting can update before final cleanup. A live queue record must
    # also be terminal/absent before the project guard is inspected.
    try:live=command(['squeue','-h','-j',str(job),'-o','%T'])
    except subprocess.CalledProcessError as error:
        if 'invalid job id' not in (error.stderr or '').lower():raise
        live=''
    return all(line.strip().split('+',1)[0] in TERMINAL for line in live.splitlines())


def handover(project,old,cpus,cpu_limit=1600,wait_seconds=60,poll_seconds=10):
    project=Path(project).resolve();old=str(old);replacement=None
    if not old.isdigit() or cpus<1 or cpu_limit<cpus:raise ValueError('Invalid job/CPU arguments')
    user=getpass.getuser();info=job_info(old)
    verify_identity(info,old,project,user)
    if info.get('JobState')!='RUNNING':raise RuntimeError('Old job is not RUNNING; inspect before using a resume command')
    current_cpus=int(info['NumCPUs'])
    if cpus<=current_cpus:raise ValueError('Replacement must request more CPUs than the current job')
    study=verify_study(project,old)
    if guard_owner(project)!=old:raise RuntimeError('The running job does not own this project guard')
    running=command(['squeue','-h','--array','-u',user,'-t','RUNNING,COMPLETING,SUSPENDED','-o','%C'])
    total=sum(int(line.strip()) for line in running.splitlines() if line.strip())
    if total<current_cpus:raise RuntimeError('Inconsistent CPU accounting; leave old job running')
    projected=total-current_cpus+cpus
    if projected>cpu_limit:raise RuntimeError(f'Projected total {projected} exceeds CPU limit {cpu_limit}; old job unchanged')
    partition=command(['scontrol','show','partition','longq','-o'])
    fields=dict(x.split('=',1) for x in partition.split() if '=' in x)
    limit=fields.get('MaxTime')
    if not limit:raise RuntimeError('Cannot determine longq MaxTime')
    if limit in {'UNLIMITED','INFINITE'}:limit='20-00:00:00'
    args=['--job-name=gs_cert_research','--partition=longq',f'--ntasks={cpus}',
        '--cpus-per-task=1','--mem-per-cpu=4G',f'--time={limit}',f'--chdir={project}',
        f'--dependency=afterany:{old}',
        '--export=ALL,GS_OJCS_STAGE=certified,GS_OJCS_PRESET=research']
    print(f'Frozen study verified: {study}\nCPUs now={total}; after replacement={projected}/{cpu_limit}',flush=True)
    # Scheduler rejection here leaves the old computation entirely untouched.
    command(['sbatch','--test-only',*args,str(project/'Batch')])
    response=command(['sbatch','--parsable','--hold',*args,str(project/'Batch')])
    replacement=response.split(';',1)[0]
    if not replacement.isdigit():raise RuntimeError(f'Unexpected submission response {response!r}; old job not cancelled')
    print(f'Replacement {replacement} accepted and HELD; old job still running.',flush=True)
    receipt=project/'outputs/cert/submissions'/f'scale-{old}-to-{replacement}.json'
    receipt.parent.mkdir(parents=True,exist_ok=True)
    if receipt.exists():raise RuntimeError(f'Receipt already exists; replacement {replacement} held; old job unchanged')
    receipt.write_text(json.dumps(dict(old_job=old,replacement_job=replacement,study=study,
        cpus=cpus,projected_user_cpus=projected,created_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
    print(f'Receipt: {receipt}\nStopping only job {old}; waiting for cleanup.',flush=True)
    try:
        # Recheck immediately before touching the old job. --full signals the
        # batch shell as well as its children so its EXIT guard cleanup can run.
        verify_identity(job_info(old),old,project,user)
        command(['scancel','--full',old])
        deadline=time.monotonic()+wait_seconds
        while not old_job_ended(old):
            if time.monotonic()>=deadline:raise RuntimeError('Old job cleanup/accounting still pending')
            time.sleep(min(poll_seconds,max(0,deadline-time.monotonic())))
        owner=guard_owner(project)
        if owner is not None:raise RuntimeError(f'Project guard remains (owner {owner}); it has NOT been removed')
        command(['scontrol','release',replacement])
    except Exception as error:
        detail=(getattr(error,'stderr',None) or str(error)).strip()
        raise RuntimeError(f'{detail}. Replacement {replacement} remains HELD; inspect old job/guard before releasing it. Receipt: {receipt}') from error
    print(f'Released replacement job {replacement}; it will reuse completed shards.\n'
          f'Monitor: bash {project}/hpc/monitor.sh {replacement}',flush=True)
    return replacement


def recover(project,old,replacement):
    """Recover a specific held replacement; never submit or cancel any job."""
    project=Path(project).resolve();old=str(old);replacement=str(replacement)
    if not old.isdigit() or not replacement.isdigit() or old==replacement:
        raise ValueError('Two different numeric job IDs are required')
    receipt_path=project/'outputs/cert/submissions'/f'scale-{old}-to-{replacement}.json'
    receipt=json.loads(receipt_path.read_text())
    if str(receipt.get('old_job'))!=old or str(receipt.get('replacement_job'))!=replacement:
        raise RuntimeError('Handover receipt does not match the requested job pair')
    study=verify_study(project,old)
    if receipt.get('study')!=study:raise RuntimeError('Receipt/frozen study mismatch')
    info=job_info(replacement)
    verify_identity(info,replacement,project,getpass.getuser())
    if (info.get('JobState')!='PENDING' or info.get('Priority')!='0'
            or int(info.get('NumCPUs','0'))!=receipt.get('cpus')):
        raise RuntimeError('Replacement is not held/pending with the recorded CPU count; no guard changed')
    if not old_job_ended(old):raise RuntimeError('Old job is still active or termination is unconfirmed; no guard changed')
    guard=project/'outputs/ojcs/.campaign.guard';archive=None
    if guard.is_symlink():raise RuntimeError('Refusing a symlink project guard')
    owner=guard_owner(project)
    if owner is not None:
        if owner!=old:raise RuntimeError(f'Guard owner is {owner}, not terminated job {old}; no guard changed')
        owner_bytes=(guard/'owner').read_bytes()
        # Recheck just before the only filesystem mutation. A different guard
        # or a requeued old job must never be mistaken for a stale owner.
        if not old_job_ended(old) or (guard/'owner').read_bytes()!=owner_bytes:
            raise RuntimeError('Job/guard changed during verification; replacement stays held')
        archive=project/'outputs/cert/guard-recovery'/f'guard-{old}-for-{replacement}-{time.time_ns()}'
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists():raise RuntimeError('Archive path already exists')
        guard.rename(archive)  # preserve the entire old directory, never delete
        print(f'Archived terminated job {old} guard: {archive}',flush=True)
    else:
        print('Project guard is already clear.',flush=True)
    command(['scontrol','release',replacement])
    print(f'Released existing replacement {replacement}; no new job was submitted.\n'
          f'Frozen study: {study}\nMonitor: bash {project}/hpc/monitor.sh {replacement}',flush=True)
    return archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=Path('/home/tariq.qayyum/hpc/GapSlice-OJCS'))
    parser.add_argument('--from-job',required=True)
    parser.add_argument('--replacement-job',help='Recover an existing held replacement; archive a verified terminated owner guard')
    parser.add_argument('--cpus',type=int,default=1280)
    parser.add_argument('--cpu-limit',type=int,default=1600)
    parser.add_argument('--wait-seconds',type=int,default=60)
    args=parser.parse_args()
    if args.wait_seconds<0:parser.error('wait-seconds must be nonnegative')
    try:
        if args.replacement_job:recover(args.project,args.from_job,args.replacement_job)
        else:handover(args.project,args.from_job,args.cpus,args.cpu_limit,args.wait_seconds)
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as error:
        detail=getattr(error,'stderr',None) or str(error)
        print(f'ERROR: {detail}',file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
