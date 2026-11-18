from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from gapslice.certified import campaign as c
from gapslice.certified.simulator import Policy,Model
from gapslice.certified.profiles import Profile


class CampaignTests(unittest.TestCase):
    def test_risk_family_size_and_rejection_of_tiny_calibration(self):
        p=c.protocol('smoke');bank=c.design_bank('smoke');study={'protocol':p}
        cells={(candidate['id'],'nominal'):dict(k=0,n=16,reward_sum=8.) for candidate in bank}
        q=c.qualification(study,bank,cells)
        self.assertEqual(q['risk_tests'],10)
        self.assertTrue(all(not r['qualified'] for r in q['records']))

    def test_design_selection_never_reads_calibration_or_test(self):
        bank=[];cells={}
        for mode,phase,layout,kp,kd,omega in [('fused',0,'parallel',.8,1.8,8.),('fused',0,'serial',.8,1.8,8.)]:
            p=Profile(n_trucks=3,phase=phase,layout=layout)
            candidate=c.make_candidate(p,Policy(controller=mode,kp=kp,kd=kd,observer_bandwidth=omega))
            bank.append(candidate)
            for env in ['nominal','correlated','blocked']:cells[candidate['id'],env]=dict(n=64,k=0,reward_sum=25.)
        s=dict(protocol=c.protocol('research'),candidate_bank=bank)
        chosen=c.screen(s,cells)
        self.assertEqual(len(chosen['selected']),2);self.assertFalse(chosen['qualification_data_used'])
        self.assertEqual({x['profile']['layout'] for x in chosen['selected']},{'parallel','serial'})

    def test_fixed_size_paired_shards_and_independent_splits(self):
        bank=c.design_bank('smoke');study={'protocol':c.protocol('smoke')}
        a=c.replay_tasks(study,bank,'calibration');b=c.replay_tasks(study,bank,'test')
        self.assertEqual(len(a),4);self.assertTrue({x['id'] for x in a}.isdisjoint(x['id'] for x in b))
        self.assertTrue(all(x['config']['episodes']==8 for x in a+b))

    def test_immutable_artifact_and_raw_checksum(self):
        with tempfile.TemporaryDirectory(dir=c.ROOT/'tmp') as folder:
            p=Path(folder)/'value.json';c.immutable(p,{'tuple':(1,2)})
            c.immutable(p,{'tuple':(1,2)})
            with self.assertRaises(RuntimeError):c.immutable(p,{'tuple':(1,3)})
            item=c.task(c.design_bank('smoke')[0],'nominal','test',1,8,asdict(Model()))
            m=Path(folder)/'manifest.json';r=c.result_path(m,item['id']);r.parent.mkdir(parents=True)
            data=r.with_suffix('.npz');np.savez_compressed(data,values=np.arange(8))
            c.atomic_json(r,dict(task_id=item['id'],config=item['config'],raw_sha256=c.digest(data)))
            self.assertIsNotNone(c.result(m,item))
            data.write_bytes(b'altered')
            with self.assertRaises(RuntimeError):c.result(m,item)

    def test_allocation_scenarios_keep_risk_units_and_phase_restrictions(self):
        p=Profile(n_trucks=3,phase=2);candidate=c.make_candidate(p,Policy())
        q=dict(records=[dict(candidate=candidate,qualified=True,domain='nominal',risk_units=4,benefit_microseconds=200000)])
        tasks=c.allocation_tasks({'protocol':c.protocol('smoke')},q)
        sync=[t for t in tasks if t['config']['variant']=='fused_synchronous'][0]
        full=[t for t in tasks if t['config']['variant']=='fused'][0]
        self.assertTrue(all(not menu for menu in sync['config']['menus'].values()))
        self.assertEqual(full['config']['risk_costs'][p.key],4)

class SubmissionTests(unittest.TestCase):
    def launcher(self,fail_long=False):
        import os,subprocess,sys
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        (root/'hpc').mkdir();(root/'.venv/bin').mkdir(parents=True)
        (root/'.venv/bin/python').write_text('#!/bin/sh\nexit 0\n');(root/'.venv/bin/python').chmod(0o700)
        (root/'Batch').write_text((c.ROOT/'Batch').read_text())
        script=(c.ROOT/'hpc/run_certified.sh').read_text().replace('PROJECT=/home/tariq.qayyum/hpc/GapSlice-OJCS',f'PROJECT={root}')
        (root/'hpc/run_certified.sh').write_text(script)
        (root/'bin').mkdir()
        header=f'#!{sys.executable}\n'
        (root/'bin/scontrol').write_text(header+'import sys\nprint("PartitionName="+sys.argv[3]+" MaxTime=20-00:00:00")\n')
        stub=header+'''import sys,json,os
from pathlib import Path
log=Path(os.environ['MOCK_LOG']);args=sys.argv[1:]
with log.open('a') as f:f.write(json.dumps(args)+'\\n')
if '--test-only' in args:
    if os.environ.get('FAIL_LONG')=='1' and '--partition=longq' in args:sys.exit(1)
    sys.exit(0)
count=sum('--test-only' not in json.loads(line) for line in log.read_text().splitlines())
print(100+count)
'''
        (root/'bin/sbatch').write_text(stub)
        for path in (root/'bin').iterdir():path.chmod(0o700)
        env=dict(os.environ,PATH=str(root/'bin')+os.pathsep+os.environ['PATH'],MOCK_LOG=str(root/'calls.jsonl'),FAIL_LONG=str(int(fail_long)))
        run=subprocess.run(['bash',str(root/'hpc/run_certified.sh'),'research'],env=env,text=True,capture_output=True)
        events=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
        return run,events

    def test_preflight_then_smoke_then_dependent_research(self):
        run,events=self.launcher();self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(len(events),4);self.assertTrue(all('--test-only' in x for x in events[:2]))
        self.assertIn('--ntasks=160',events[3]);self.assertIn('--dependency=afterok:101',events[3])
        self.assertFalse(any('gres' in arg or 'gpu' in arg for x in events for arg in x))

    def test_scheduler_rejection_submits_nothing(self):
        run,events=self.launcher(True);self.assertNotEqual(run.returncode,0)
        self.assertEqual(len(events),2);self.assertTrue(all('--test-only' in x for x in events))
