"""Fail closed when an exported scientific event or denominator is altered."""
from copy import deepcopy
import unittest

from scripts.analyze_guard_pilot import check_record,power,paired_effect


class PilotEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record=dict(config=dict(episodes=4,model=dict(maximum_tracking_error_m=5.,minimum_clearance_m=2.,horizon_s=40.)),
            metrics=dict(episodes=4,episode_violation=[0,1,1,1],peak_error_m=[1.,6.,1.,1.],
                minimum_clearance_m=[3.,3.,1.,3.],maximum_packet_age_s=[.1]*4,
                episode_packet_loss_fraction=[0.,.25,.5,1.],completion_time_s=[10.,10.,10.,None],
                failures=3,tracking_failures=1,clearance_failures=1,completion_failures=1,
                observed_nonpositive_clearance=0,packet_trials_per_episode=4,packet_failures=7))

    def test_valid_joint_event_preserves_completion_failures(self):
        check_record(self.record)

    def test_false_joint_event_is_rejected(self):
        self.record['metrics']['episode_violation'][3]=0
        with self.assertRaisesRegex(ValueError,'Joint outcome'):check_record(self.record)

    def test_changed_component_count_is_rejected(self):
        self.record['metrics']['tracking_failures']=0
        with self.assertRaisesRegex(ValueError,'Event-count'):check_record(self.record)

    def test_missing_episode_and_nonfinite_values_are_rejected(self):
        shortened=deepcopy(self.record);shortened['metrics']['peak_error_m'].pop()
        with self.assertRaisesRegex(ValueError,'length'):check_record(shortened)
        self.record['metrics']['peak_error_m'][0]=float('nan')
        with self.assertRaises(ValueError):check_record(self.record)

    def test_packet_denominator_tampering_is_rejected(self):
        self.record['metrics']['packet_failures']=8
        with self.assertRaisesRegex(ValueError,'Packet accounting'):check_record(self.record)

    def test_null_rejection_probability_respects_test_level(self):
        null=power(100,.05,.05,.05)
        alternative=power(100,.05,.01,.05)
        self.assertLessEqual(null['power'],.05)
        self.assertGreater(alternative['power'],null['power'])

    def test_uniform_paired_difference_does_not_create_zero_width_certainty(self):
        def row(seed,value):
            return dict(config=dict(seed=seed),metrics=dict(episode_violation=[value]*50))
        effect=paired_effect([row(s,1) for s in range(4)],[row(s,0) for s in range(4)])
        self.assertEqual(effect['mean'],1.)
        self.assertLess(effect['conservative_paired_exact_95'][0],1.)
        self.assertEqual(effect['conservative_paired_exact_95'][1],1.)


if __name__=='__main__':unittest.main()
