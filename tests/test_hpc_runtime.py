"""Operational adapter failure/identity checks; no real Slurm calls."""
from contextlib import redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('certified_runtime', ROOT / 'scripts/certified_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.path = self.base / 'design/manifest.json'
        self.path.parent.mkdir()
        self.settings = dict(cpus=4, nodes=2, per_node=2, metadata_prefetch_threads=2,
                             adapter=str(ROOT / 'scripts/certified_runtime.py'))

    def test_budget_uses_actual_qos_not_claimed_1600(self):
        qos = 'limit|cpu=1000,gres/gpu=4|'
        self.assertEqual(runtime.cpu_budget(qos, '96\n24\n24\n4\n4\n4\n4\n2\n', 768), (162, 1000))
        with self.assertRaisesRegex(RuntimeError, '1442/1000'):
            runtime.cpu_budget(qos, '162', 1280)
        with self.assertRaises(RuntimeError):
            runtime.cpu_budget('limit||', '', 768)

    def test_compact_geometry_and_generated_batch(self):
        self.assertEqual(runtime.geometry(768, 64), 12)
        with self.assertRaises(ValueError):
            runtime.geometry(768, 63)
        original = (ROOT / 'Batch').read_text()
        generated = runtime.batch_text(original, Path('/project/adapter.py'), Path('/project/spec.json'))
        self.assertEqual(generated.replace('"$PY" /project/adapter.py run --spec /project/spec.json --workers "$SLURM_NTASKS"', runtime.DISPATCH), original)
        subprocess.run(['bash', '-n'], input=generated, text=True, check=True)
        flags = runtime.step_args(dict(cpus=768, per_node=64, nodes=12), self.base, 'worker')
        for flag in ['--nodes=12', '--ntasks=768', '--ntasks-per-node=64', '--distribution=block:block', '--kill-on-bad-exit=1']:
            self.assertIn(flag, flags)
        self.assertFalse(any('gpu' in arg or 'gres' in arg for arg in flags))

    def test_transient_heartbeat_rename_is_retried(self):
        writer = Mock(side_effect=[FileNotFoundError('lost temp'), None])
        pause = Mock()
        self.assertTrue(runtime.optional_heartbeat(writer, self.base / 'heartbeat.json', {'n': 10}, pause=pause))
        self.assertEqual(writer.call_count, 2)
        pause.assert_called_once()

    def test_rename_replay_with_exact_committed_value_is_success(self):
        path = self.base / 'heartbeat.json'
        path.write_text('{"n": 10}')
        writer = Mock(side_effect=FileNotFoundError('rename replay'))
        self.assertTrue(runtime.optional_heartbeat(writer, path, {'n': 10}, pause=Mock()))
        self.assertEqual(writer.call_count, 1)

    def test_optional_monitor_failure_does_not_mask_scientific_write_failure(self):
        writer = Mock(side_effect=FileNotFoundError('storage unavailable'))
        c = SimpleNamespace(atomic_json=writer)
        telemetry = self.path.parent / 'workers/job/000.json'
        with runtime.telemetry_adapter(c, self.path, 'job'):
            with redirect_stderr(io.StringIO()) as warnings, patch.object(
                    runtime, 'optional_heartbeat', side_effect=runtime_optional):
                self.assertFalse(c.atomic_json(telemetry, {'n': 10}))
            self.assertIn('optional heartbeat', warnings.getvalue())
            for path in [self.path.parent / 'results/aa/task.json', self.path.parent / 'results/aa/task.failed.json',
                         self.path.parent / 'workers/another-job/000.json']:
                with self.assertRaises(FileNotFoundError):
                    c.atomic_json(path, {'required': True})
        self.assertIs(c.atomic_json, writer)

    def test_prefetch_maintains_order_and_propagates_validation_errors(self):
        items = [{'id': str(i)} for i in range(20)]

        def read(path, item):
            time.sleep((3 - int(item['id']) % 4) * .001)
            return {'id': item['id']}

        values = list(runtime.ordered_results(read, self.path, items, threads=3))
        self.assertEqual([v['id'] for _, v in values], [x['id'] for x in items])
        with self.assertRaisesRegex(RuntimeError, 'bad hash'):
            list(runtime.ordered_results(Mock(side_effect=RuntimeError('bad hash')), self.path, items, 2))

    def test_original_aggregation_arithmetic_is_unchanged(self):
        # This sum changes if reductions are regrouped: original order is required.
        items = [dict(id=str(i)) for i in range(4)]
        values = [1e16, 1., -1e16, 1.]
        c = SimpleNamespace(read_manifest=Mock(return_value=dict(name='design', tasks=items)),
                            result=lambda path, item: values[int(item['id'])])

        def original(path):
            answer = 0.
            for item in c.read_manifest(path)['tasks']:
                answer += c.result(path, item)
            return answer

        reader, manifest_reader = c.result, c.read_manifest
        self.assertEqual(original(self.path), 1.)
        self.assertEqual(runtime.ordered_aggregate(c, original, self.path, 2), 1.)
        self.assertIs(c.result, reader)
        self.assertIs(c.read_manifest, manifest_reader)
        # Only one manifest is held by the adapter/original aggregate together.
        self.assertEqual(manifest_reader.call_count, 2)

    def fake_campaign(self, name='design'):
        m = dict(name=name, study='study', tasks=[dict(id='a'), dict(id='b')])
        return SimpleNamespace(ROOT=self.base, read_manifest=Mock(return_value=m),
                               result=Mock(), atomic_json=runtime.write_json, digest=Mock(return_value='sha'))

    def test_worker_step_failure_exits_without_cached_result_scan(self):
        c = self.fake_campaign()
        with patch.dict(os.environ, GS_OJCS_ATTEMPT='new'), patch.object(runtime.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, 'stopped without scanning'):
                runtime.execute(c, self.settings, self.base / 'spec.json', self.base / 'runtime', self.path, 'tables', 4, False)
        c.result.assert_not_called()
        self.assertEqual(json.loads((self.base / 'runtime/failure.json').read_text())['phase'], 'design')
        self.assertFalse((self.path.parent / 'summary.json').exists())

    def test_completed_stage_skips_workers_but_still_uses_original_aggregate(self):
        c = self.fake_campaign()
        prior = dict(stage='design', expected=2, complete=2, failed_or_pending=0,
                     worker_exit_code=0, manifest=str(self.path))
        runtime.write_json(self.path.parent / 'summary.json', prior)
        with patch.object(runtime.subprocess, 'run') as launch:
            runtime.execute(c, self.settings, self.base / 'spec.json', self.base / 'runtime', self.path, 'tables', 4, False)
        launch.assert_not_called()
        self.assertTrue((self.base / 'runtime/design-reused.json').exists())
        # The driver always aggregates after this scheduling shortcut. A bad
        # result still fails through the ORIGINAL validator, even in reused data.
        from gapslice.certified import campaign as scientific
        reader, manifest_reader = scientific.result, scientific.read_manifest
        with patch.object(scientific, 'read_manifest', c.read_manifest), patch.object(scientific, 'result', side_effect=RuntimeError('bad raw hash')):
            with self.assertRaisesRegex(RuntimeError, 'bad raw hash'):
                runtime.ordered_aggregate(scientific, scientific.aggregate, self.path, 2)
        self.assertIs(scientific.result, reader)
        self.assertIs(scientific.read_manifest, manifest_reader)

    def test_probe_requires_every_rank_and_compact_host_coverage(self):
        records = self.base / 'records'
        for rank in range(4):
            runtime.write_json(records / f'{rank:04d}.json',
                               dict(rank=rank, size=4, local_rank=rank % 2, host=f'cn{rank // 2}'))
        self.assertTrue(runtime.validate_probe(records, self.settings)['passed'])
        runtime.write_json(records / '0003.json', dict(rank=3, size=4, local_rank=0, host='cn4'))
        with self.assertRaisesRegex(RuntimeError, 'not compact'):
            runtime.validate_probe(records, self.settings)
        (records / '0003.json').unlink()
        with self.assertRaises(FileNotFoundError):
            runtime.validate_probe(records, self.settings)

    def test_failed_probe_never_enters_scientific_pipeline(self):
        with patch.object(runtime.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, 'no scientific work started'):
                runtime.run_probe(self.settings, self.base / 'spec.json', self.base / 'runtime')
        self.assertEqual(json.loads((self.base / 'runtime/failure.json').read_text())['phase'], 'probe')

    def test_run_exits_before_science_when_probe_fails(self):
        batch = self.base / 'Batch'
        batch.write_text('original batch')
        c = SimpleNamespace(ROOT=self.base, read_study=Mock(return_value={'id': 'study'}),
                            source=Mock(return_value={'frozen': True}), run=Mock())
        settings = dict(self.settings, project=str(self.base), study=str(self.path.parent), study_id='study',
                        base_source={'frozen': True}, base_batch_sha256=runtime.digest(batch))
        spec_path = self.base / 'spec.json'
        runtime.write_json(spec_path, settings)
        with patch.dict(os.environ, SLURM_NTASKS='4', SLURM_JOB_NUM_NODES='2', SLURM_JOB_ID='new'), patch.object(
                runtime, 'campaign', return_value=c), patch.object(runtime, 'run_probe', side_effect=RuntimeError('probe failed')), patch.object(
                runtime.subprocess, 'run', return_value=SimpleNamespace(stdout='slurm 23.02.8')):
            with self.assertRaisesRegex(RuntimeError, 'probe failed'):
                runtime.run(settings, spec_path, 4)
        c.run.assert_not_called()
        self.assertEqual(json.loads((self.path.parent / 'runtime/new/provenance.json').read_text())['status'], 'failed')

    def test_adapter_snapshot_tampering_is_detected(self):
        control = self.base / 'outputs/cert/runtime/test'
        control.mkdir(parents=True)
        batch = control / 'Batch'
        batch.write_text('batch')
        spec_path = control / 'spec.json'
        settings = dict(self.settings, version=runtime.VERSION, project=str(self.base),
                        adapter_sha256=runtime.digest(runtime.__file__), batch=str(batch),
                        batch_sha256=runtime.digest(batch))
        runtime.write_json(spec_path, settings)
        self.assertEqual(runtime.load_spec(spec_path), settings)
        batch.write_text('edited after submission')
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            runtime.load_spec(spec_path)


# Keep the real retry implementation available when routing it through a mock.
real_optional = runtime.optional_heartbeat


def runtime_optional(writer, path, value):
    return real_optional(writer, path, value, pause=Mock())


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / 'Batch').write_text((ROOT / 'Batch').read_text())
        mapping = self.project / 'outputs/cert/jobs/3111745.study'
        mapping.parent.mkdir(parents=True)
        mapping.write_text(str(self.project / 'outputs/cert/studies/frozen') + '\n')
        self.events, self.receipts = [], []
        self.h = SimpleNamespace(verify_study=Mock(return_value='frozen'), old_job_ended=Mock(return_value=True),
                                  guard_owner=Mock(return_value='3111745'), recover=Mock(), command=self.command)
        for target, value in [('DEFAULT_PROJECT', self.project), ('helper', Mock(return_value=self.h)),
                              ('campaign', Mock(return_value=SimpleNamespace(source=lambda: {'source': 'frozen'})))]:
            p = patch.object(runtime, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(runtime.getpass, 'getuser', return_value='tariq.qayyum')
        p.start()
        self.addCleanup(p.stop)

    def command(self, args):
        self.events.append(args)
        if args[0] == 'sacct':
            return '3111745|tariq.qayyum|gs_cert_research|'
        if args[0] == 'sacctmgr':
            return 'limit|cpu=1000,gres/gpu=4|'
        if args[0] == 'squeue':
            return '162'
        if args[:3] == ['scontrol', 'show', 'partition']:
            return 'PartitionName=longq MaxTime=20-00:00:00'
        if args[0] == 'sbatch':
            return '' if '--test-only' in args else '3112000;slurm'
        raise AssertionError(args)

    def test_frozen_snapshot_compact_held_submission_and_recovery(self):
        self.assertEqual(runtime.submit(self.project, '3111745'), '3112000')
        requests = [args for args in self.events if args[0] == 'sbatch']
        self.assertEqual(len(requests), 2)
        self.assertIn('--test-only', requests[0])
        self.assertIn('--hold', requests[1])
        for arg in ['--nodes=12', '--ntasks=768', '--ntasks-per-node=64', '--qos=limit', '--time=20-00:00:00']:
            self.assertIn(arg, requests[1])
        self.assertEqual((self.project / 'Batch').read_bytes(), (ROOT / 'Batch').read_bytes())
        self.assertFalse(any(args[0] == 'scancel' for args in self.events))
        receipt = json.loads((self.project / 'outputs/cert/submissions/scale-3111745-to-3112000.json').read_text())
        s = json.loads(Path(receipt['runtime_spec']).read_text())
        self.assertEqual(s['adapter_sha256'], runtime.digest(s['adapter']))
        self.assertEqual(s['batch_sha256'], runtime.digest(s['batch']))
        self.assertEqual(s['base_source'], {'source': 'frozen'})
        self.h.recover.assert_called_once_with(self.project, '3111745', '3112000')

    def test_active_old_job_or_over_quota_request_never_submits(self):
        self.h.old_job_ended.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'still active'):
            runtime.submit(self.project, '3111745')
        self.assertFalse(self.events)
        self.h.old_job_ended.return_value = True
        with self.assertRaisesRegex(RuntimeError, '1442/1000'):
            runtime.submit(self.project, '3111745', cpus=1280)
        self.assertFalse(any(args[0] == 'sbatch' for args in self.events))

    def test_wrong_guard_owner_never_submits(self):
        self.h.guard_owner.return_value = 'another-project-job'
        with self.assertRaisesRegex(RuntimeError, 'guard belongs'):
            runtime.submit(self.project, '3111745')
        self.assertFalse(self.events)


if __name__ == '__main__':
    unittest.main()
