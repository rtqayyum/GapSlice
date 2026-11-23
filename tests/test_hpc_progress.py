"""Read-only monitoring semantics: cached work must never count as fresh speed."""
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('progress', ROOT / 'scripts/certified_progress.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.study = self.project / 'outputs/cert/studies/frozen'
        self.study.mkdir(parents=True)

    def log(self, attempt, stage, text):
        path = self.project / 'logs/frozen' / attempt / stage / 'progress-000.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def snapshots(self):
        before = dict(sampled_at=100., stages={s: dict(done=set(), fresh=set(), reused=set(), failed=set()) for s in p.STAGES})
        before['stages']['calibration']['done'] = set(range(50))
        before['stages']['calibration']['reused'] = set(range(50))
        after = copy.deepcopy(before)
        after['sampled_at'] = 160.
        after['stages']['calibration']['done'].update(range(50, 60))
        after['stages']['calibration']['fresh'].update(range(50, 60))
        return before, after

    def test_deduplicates_attempts_and_ignores_resume_for_fresh_work(self):
        a, b, failed = 'a' * 24, 'b' * 24, 'c' * 24
        old = self.log('old', 'calibration', f'COMPLETE task={a}\nCOMPLETE task={a}\n')
        current = self.log('current', 'calibration', f'RESUME task={a}\nCOMPLETE task={b}\nFAILED task={failed}\nCOMPLETE task={failed}')
        original = {x: (x.stat().st_mtime_ns, x.read_bytes()) for x in (old, current)}
        snap = p.snapshot(self.project, self.study, 'current')['stages']['calibration']
        self.assertEqual(snap['done'], {a, b})
        self.assertEqual(snap['fresh'], {b})
        self.assertEqual(snap['reused'], {a})
        self.assertEqual(snap['failed'], {failed})
        self.assertEqual({x: (x.stat().st_mtime_ns, x.read_bytes()) for x in (old, current)}, original)

    def test_eta_uses_sampled_fresh_delta_only(self):
        before, after = self.snapshots()
        # 140 left / (10 fresh / 60 sec) = 840 sec = 0.2 h after rounding.
        estimate = p.estimate(before, after, dict(calibration=100, test=100), 'RUNNING')
        self.assertIn('10 shards / 60s = 600 shards/hour', estimate)
        self.assertIn('Remaining main shards: 140', estimate)
        self.assertIn('0.2 hours', estimate)

    def test_no_rate_from_reused_work_or_inactive_failed_job(self):
        before, after = self.snapshots()
        after['stages']['calibration']['fresh'].clear()
        self.assertIn('only 0 fresh', p.estimate(before, after, dict(calibration=100, test=100), 'RUNNING'))
        self.assertIn('state is FAILED', p.estimate(before, after, {}, 'FAILED'))
        after['stages']['calibration']['failed'].add('unresolved')
        self.assertIn('unresolved failed', p.estimate(before, after, dict(calibration=100, test=100), 'RUNNING'))

    def test_protocol_totals_without_loading_large_bank(self):
        protocol = dict(environments=['a', 'b', 'c'], calibration_n=32768, test_n=32768, batch=2048)
        (self.study / 'study.json').write_text(json.dumps(dict(protocol=protocol, candidate_bank=['unused'] * 100000), indent=2))
        (self.study / 'selection.json').write_text(json.dumps(dict(selected=[None] * 3623)))
        self.assertEqual(p.expected(self.study), dict(calibration=173904, test=173904))

    def test_terminal_accounting_overrides_absent_live_queue(self):
        def command(args):
            if args[0] == 'squeue':
                return '', '', 0
            return '3111761|FAILED|0:53|00:00:01|768||\n3111761.batch|CANCELLED|0:53|00:00:01|64||', '', 0
        with patch.object(p, 'command', side_effect=command), redirect_stdout(io.StringIO()):
            self.assertEqual(p.accounting('3111761'), 'FAILED')


if __name__ == '__main__':
    unittest.main()
