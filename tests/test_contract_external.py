from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
import numpy as np
from contractlab.ldpc import frame,Lookup
from contractlab.external import native_ccc,episode
from contractlab.simulator import simulate
from contractlab.specs import Policy,Model
from gapslice.certified.profiles import Profile
from gapslice.certified.safety import ensure_tables
from gapslice.guard.simulator import ENVIRONMENTS

ROOT=Path(__file__).resolve().parents[1]


class ExternalTests(unittest.TestCase):
    def test_all_transport_modulations_roundtrip_without_noise(self):
        for prbs in [10,20,40]:
            for payload in [300,600]:
                result=frame(prbs,payload,20,8187,noise=False)
                self.assertFalse(result['failed'],result)

    def test_native_ccc_unsafe_and_filtered_are_distinguished(self):
        rows=native_ccc()['results']
        self.assertGreater(rows[0]['minimum_th_barrier'],0)
        self.assertLess(rows[1]['minimum_th_barrier'],0)
        self.assertGreaterEqual(rows[2]['minimum_th_barrier'],0)

    def test_no_radio_age_is_missing_and_reference_is_not_completion(self):
        tables=ensure_tables(ROOT/'outputs/contracts/unit-tables')
        p=Profile(n_trucks=3,h_target=.9,prbs=0,copies=0,pattern='none',layout='none')
        result=simulate(p,Policy(reference_rate=.0001),ENVIRONMENTS['nominal'],814,2,'verification',tables,
            Model(horizon_s=10.,radio_mode='absent'))
        self.assertEqual(result['maximum_packet_age_s'],[None,None])
        self.assertEqual(result['startup_missing_fraction'],[1.,1.])
        self.assertEqual(result['completion_failures'],2)
        self.assertTrue(all(x>9.9 for x in result['longest_packet_outage_s']))

    def test_sumo_native_acc_cacc_and_custom_controller_execute(self):
        tables=ensure_tables(ROOT/'outputs/contracts/unit-tables')
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as td:
            for mode in ['SUMO_IDM','SUMO_ACC','SUMO_CACC','hold']:
                result=episode(Path(td)/mode,mode,8187,tables,n=3,horizon=1.)
                self.assertTrue(np.isfinite(result['minimum_clearance_m']))
                self.assertEqual(result['backend'],mode)

if __name__=='__main__':unittest.main()
