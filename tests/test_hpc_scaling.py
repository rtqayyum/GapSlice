"""Control-plane handover checks; never call a real Slurm command."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('scale_certified',ROOT/'scripts/scale_certified.py')
scale=importlib.util.module_from_spec(spec);spec.loader.exec_module(scale)


class ScalingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        self.project=Path(self.temp.name).resolve();self.events=[];self.flags=set()
        self.guard=self.project/'outputs/ojcs/.campaign.guard';self.guard.mkdir(parents=True)
        (self.guard/'owner').write_text('job_id=3098836\ntoken=owned\n')
        self.raw=self.project/'outputs/cert/studies/frozen/results/keep.npz'
        self.raw.parent.mkdir(parents=True);self.raw.write_bytes(b'completed scientific result')
        for name,value in [('command',self.command),('verify_study',lambda *args:'frozen-study')]:
            patcher=patch.object(scale,name,side_effect=value);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(scale.getpass,'getuser',return_value='tariq.qayyum');patcher.start();self.addCleanup(patcher.stop)

    def command(self,args):
        self.events.append(args)
        if args[:3]==['scontrol','show','job']:
            project='/another/project' if 'wrong_project' in self.flags else str(self.project)
            return (f'JobId=3098836 JobName=gs_cert_research WorkDir={project} '
                    'UserId=tariq.qayyum(1) JobState=RUNNING NumCPUs=160')
        if args[:3]==['scontrol','show','partition']:return 'PartitionName=longq MaxTime=20-00:00:00'
        if args[0]=='squeue':
            if '-u' in args:return '96\n160\n24\n24\n4\n4\n4\n4\n2'
            return 'COMPLETING' if 'slow_cleanup' in self.flags else ''
        if args[0]=='sacct':return '3098836|CANCELLED by 1|'
        if args[0]=='sbatch':
            if '--test-only' in args:
                if 'reject_preflight' in self.flags:raise subprocess.CalledProcessError(1,args,stderr='account limit')
                return ''
            if 'reject_submission' in self.flags:raise subprocess.CalledProcessError(1,args,stderr='submission rejected')
            return '3112000;slurm'
        if args[0]=='scancel':
            self.assertEqual(args,['scancel','--full','3098836'])
            if 'stale_guard' not in self.flags:
                (self.guard/'owner').unlink();self.guard.rmdir()
            return ''
        if args[:2]==['scontrol','release']:return ''
        raise AssertionError(f'Unexpected scheduler call: {args}')

    def run_handover(self,**kwargs):
        return scale.handover(self.project,'3098836',kwargs.pop('cpus',1280),wait_seconds=0,**kwargs)

    def cancelled(self):return [x for x in self.events if x[0]=='scancel']

    def released(self):return [x for x in self.events if x[:2]==['scontrol','release']]

    def test_submit_held_before_cancel_then_release_preserves_results(self):
        self.assertEqual(self.run_handover(),'3112000')
        submitted=next(i for i,x in enumerate(self.events) if x[0]=='sbatch' and '--hold' in x)
        cancelled=next(i for i,x in enumerate(self.events) if x[0]=='scancel')
        released=next(i for i,x in enumerate(self.events) if x[:2]==['scontrol','release'])
        self.assertLess(submitted,cancelled);self.assertLess(cancelled,released)
        request=self.events[submitted]
        for value in ['--ntasks=1280','--mem-per-cpu=4G','--dependency=afterany:3098836','--hold']:
            self.assertIn(value,request)
        self.assertFalse(any('gpu' in value or 'gres' in value for value in request))
        receipt=json.loads((self.project/'outputs/cert/submissions/scale-3098836-to-3112000.json').read_text())
        self.assertEqual(receipt['projected_user_cpus'],1442)
        self.assertEqual(self.raw.read_bytes(),b'completed scientific result')

    def test_preflight_rejection_keeps_old_job_running(self):
        self.flags.add('reject_preflight')
        with self.assertRaises(subprocess.CalledProcessError):self.run_handover()
        self.assertFalse(self.cancelled());self.assertFalse(self.released());self.assertTrue(self.guard.exists())
        self.assertFalse(any('--hold' in x for x in self.events))

    def test_submission_rejection_keeps_old_job_running(self):
        self.flags.add('reject_submission')
        with self.assertRaises(subprocess.CalledProcessError):self.run_handover()
        self.assertFalse(self.cancelled());self.assertTrue(self.guard.exists())

    def test_wrong_project_is_never_cancelled(self):
        self.flags.add('wrong_project')
        with self.assertRaisesRegex(RuntimeError,'identity'):self.run_handover()
        self.assertFalse(self.cancelled());self.assertFalse(any(x[0]=='sbatch' for x in self.events))

    def test_changed_source_is_never_interrupted(self):
        with patch.object(scale,'verify_study',side_effect=RuntimeError('source changed')):
            with self.assertRaisesRegex(RuntimeError,'source changed'):self.run_handover()
        self.assertFalse(self.cancelled());self.assertTrue(self.guard.exists())

    def test_unknown_guard_owner_is_never_interrupted(self):
        (self.guard/'owner').write_text('job_id=999\n')
        with self.assertRaisesRegex(RuntimeError,'own this project guard'):self.run_handover()
        self.assertFalse(self.cancelled())

    def test_cpu_limit_checked_before_any_submission(self):
        with self.assertRaisesRegex(RuntimeError,'exceeds CPU limit'):self.run_handover(cpus=1600)
        self.assertFalse(self.cancelled());self.assertFalse(any(x[0]=='sbatch' for x in self.events))

    def test_stale_guard_preserved_and_replacement_stays_held(self):
        self.flags.add('stale_guard')
        with self.assertRaisesRegex(RuntimeError,'remains HELD'):self.run_handover()
        self.assertTrue(self.guard.exists());self.assertFalse(self.released())
        self.assertEqual(self.raw.read_bytes(),b'completed scientific result')

    def test_slow_termination_keeps_replacement_held(self):
        self.flags.add('slow_cleanup')
        with self.assertRaisesRegex(RuntimeError,'remains HELD'):self.run_handover()
        self.assertFalse(self.released())


if __name__=='__main__':unittest.main()
