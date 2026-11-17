"""Exercise failure propagation, real-task recovery and exact resumption."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from gapslice.revision import campaign
from gapslice.revision.experiments import DISPATCH


class CampaignTests(unittest.TestCase):
    def test_configuration_ids_are_unique_and_seeded(self):
        for preset, expected in [('smoke', 4), ('audit', 2004), ('full', 25308)]:
            configs = campaign.configurations(preset)
            self.assertEqual(len(configs), expected)
            self.assertEqual(configs, campaign.configurations(preset))
            self.assertEqual(len({campaign.sha(c) for c in configs}), expected)

    def test_real_task_recovers_from_failure_and_then_skips(self):
        config = dict(family='radio', h=1., beta=2., eta=.3, n_trucks=5,
                      blocked=False, payload=300, rice=3., cap=106)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(campaign.ROOT/'gapslice', root/'gapslice', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(campaign.ROOT/'requirements-hpc.txt', root/'requirements-hpc.txt')
            (root/'results').mkdir()
            for name in ['gain_curves.npz', 'tail_table.npz']:
                shutil.copy2(campaign.ROOT/'results'/name, root/'results'/name)
            with patch.object(campaign, 'configurations', return_value=[config]):
                manifest = campaign.build(root, 'smoke')
            def broken(_):
                raise RuntimeError('deliberate integration-test failure')
            with contextlib.redirect_stdout(io.StringIO()):
                with patch.dict(DISPATCH, radio=broken):
                    self.assertEqual(campaign.worker(root, manifest, 0, 1), 1)
                self.assertEqual(campaign.report(root, manifest), 1)
                self.assertEqual(campaign.worker(root, manifest, 0, 1), 0)
                self.assertEqual(campaign.report(root, manifest), 0)
                m = campaign.read_manifest(root, manifest)
                base, results, _ = campaign.locations(root, m)
                record = results/f'{m["tasks"][0]["id"]}.json'
                before = record.read_bytes()
                with patch.dict(DISPATCH, radio=broken):
                    self.assertEqual(campaign.worker(root, manifest, 0, 1), 0)
                self.assertEqual(record.read_bytes(), before)
                self.assertFalse(list(results.glob('*.failed.json')))
                summary = json.loads((base/'summary.json').read_text())
                self.assertEqual((summary['complete'], summary['failed'], summary['pending']), (1, 0, 0))
                self.assertTrue((base/'report.md').is_file())


if __name__ == '__main__':
    unittest.main()
