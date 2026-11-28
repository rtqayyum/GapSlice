from pathlib import Path
import unittest
from contractlab.hpc import resources,quota

ROOT=Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    def test_research_is_480_ranks_on_fifteen_nodes(self):
        cpus,pernode,queue=resources('research')
        self.assertEqual((cpus,pernode,queue),(480,32,'longq'));self.assertEqual(cpus//pernode,15)

    def test_effective_qos_counts_all_other_projects(self):
        self.assertEqual(quota('limit|cpu=1000,gres/gpu=4|','96\n2\n',480),(98,1000))
        with self.assertRaises(RuntimeError):quota('limit|cpu=1000|','600\n',480)
        with self.assertRaises(RuntimeError):quota('other|cpu=1600|','',480)

    def test_launcher_preserves_completed_study_and_unlimited_peer_wait(self):
        batch=(ROOT/'BatchContracts').read_text();campaign=(ROOT/'contractlab/campaign.py').read_text()
        self.assertIn('--wait=0',batch);self.assertIn("'--wait=0'",campaign)
        self.assertIn('--kill-on-bad-exit=1',batch);self.assertIn("time.sleep(40)",(ROOT/'contractlab/hpc.py').read_text())
        self.assertNotIn('--gres',batch);self.assertNotIn('scancel',batch)
        self.assertIn('gs_acquire_project_lock',batch)
        prepare=(ROOT/'hpc/contracts/prepare.sh').read_text()
        self.assertIn('--without-pip',prepare);self.assertIn('pip --python "$PY"',prepare)
        self.assertNotIn('/cm/shared/apps/anaconda3',prepare)

if __name__=='__main__':unittest.main()
