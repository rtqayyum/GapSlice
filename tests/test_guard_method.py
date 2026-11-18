"""Physical boundaries, statistical error control and separation of evidence."""
import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.stats import binom

from gapslice.guard import campaign
from gapslice.guard.compiler import compile_catalog
from gapslice.guard.phy import data_re,tbs,transport
from gapslice.guard.profiles import Profile,catalog,admit
from gapslice.guard.risk import certify,minimum_zero_failure_episodes,upper_bound
from gapslice.guard.simulator import ENVIRONMENTS,Model,gap_reference,repeat_cholesky,simulate,stream
from gapslice.revision.slot_schedule import validate


class RiskTests(unittest.TestCase):
    def test_zero_failure_sample_requirement(self):
        n=minimum_zero_failure_episodes(.01,.05)
        self.assertEqual(n,299)
        self.assertLessEqual(upper_bound(0,n,.05),.01)
        self.assertGreater(upper_bound(0,n-1,.05),.01)

    def test_count_boundaries_are_conservative(self):
        self.assertEqual(upper_bound(10,10),1.)
        with self.assertRaises(ValueError):upper_bound(-1,10)
        with self.assertRaises(ValueError):upper_bound(0,0)

    def test_exact_null_rejection_probability_is_bounded(self):
        alpha=.05;delta=.05;n=100
        rejection=sum(binom.pmf(k,n,delta) for k in range(n+1) if binom.cdf(k,n,delta)<=alpha)
        self.assertLessEqual(rejection,alpha+1e-12)

    def test_sequence_stops_at_first_failed_test(self):
        counts={'bad':{'e':dict(failures=100,episodes=1000)},'good':{'e':dict(failures=0,episodes=1000)}}
        fixed=certify(['bad','good'],counts)
        self.assertEqual(fixed['accepted'],[])
        self.assertEqual(fixed['untested'],['good'])
        self.assertEqual(certify(['bad','good'],counts,procedure='bonferroni')['accepted'],['good'])

    def test_one_bad_environment_blocks_qualification(self):
        counts={'p':{'easy':dict(failures=0,episodes=1000),'hard':dict(failures=100,episodes=1000)}}
        self.assertEqual(certify(['p'],counts)['accepted'],[])

    def test_missing_environment_and_duplicate_order_are_rejected(self):
        with self.assertRaises(ValueError):certify(['p','p'],{'p':{'e':dict(failures=0,episodes=1000)}})
        with self.assertRaises(ValueError):certify(['a','b'],{'a':{'e':dict(failures=0,episodes=1000)},'b':{}})

    def test_profile_risk_labels_are_tested_at_their_own_targets(self):
        counts={k:{'e':dict(failures=0,episodes=1000)} for k in ['loose','strict']}
        result=certify(['loose','strict'],counts,risk_targets={'loose':.01,'strict':.001})
        self.assertEqual(result['accepted'],['loose'])
        self.assertEqual(result['tested'][1]['risk_target'],.001)


class ProfileTests(unittest.TestCase):
    def test_pinned_tbs_examples_cover_small_and_segmented_branches(self):
        self.assertEqual(tbs(120,0),24)
        self.assertEqual(tbs(1000,9),1320)
        self.assertEqual(tbs(20000,0),4616)
        self.assertEqual(tbs(5000,20),16392)

    def test_payload_header_and_overheads_are_accounted_for(self):
        self.assertEqual(data_re(10),948)
        grant=transport(10,300)
        self.assertGreaterEqual(grant['tbs_bits'],8*312)
        self.assertIsNone(transport(10,1200))
        with self.assertRaises(ValueError):data_re(3)

    def test_all_catalog_profiles_pass_independent_scheduler(self):
        for n in [3,5,7]:
            for cap in [51,106]:
                for p in catalog(n_trucks=n,cap=cap,extensive=True):
                    p.check();pp=p.placements()
                    self.assertFalse(validate(pp,cap,[x.job for x in pp]))
                    self.assertEqual(len(p.cells()),p.cost)
                    self.assertEqual(len(pp),(n-1)*p.copies)
                    self.assertTrue(all(place.first_prb%10==0 and place.job.prbs%10==0 for place in pp))

    def test_hopping_is_retained_even_with_identical_occupied_cells(self):
        pp=catalog()
        spread=next(p for p in pp if p.prbs==20 and p.copies==4 and p.pattern=='spread')
        hopped=next(p for p in pp if p.prbs==20 and p.copies==4 and p.pattern=='hopped')
        self.assertEqual(spread.cells(),hopped.cells())
        self.assertNotEqual([(p.job.packet,p.first_prb) for p in spread.placements()],
                            [(p.job.packet,p.first_prb) for p in hopped.placements()])

    def test_overwide_and_unfittable_payload_profiles_are_rejected(self):
        with self.assertRaises(ValueError):Profile(7,1.5,1.,6.,20,4,'spread',cap=51).check()
        with self.assertRaises(ValueError):Profile(5,1.5,1.,6.,10,1,'clustered',payload_bytes=1200).check()

    def test_exact_small_admission_matches_constructive_optimum(self):
        p=Profile(3,1.5,1.,6.,10,1,'clustered',cap=20)
        result=admit({'a':[(p,1.)],'b':[(p,2.)],'c':[(p,3.)]},'exact')
        self.assertEqual(result['status'],'optimal')
        self.assertEqual(result['admitted'],2)
        self.assertAlmostEqual(result['utility'],5.)
        self.assertEqual(result['checked_jobs'],4)

    def test_fleet_risk_constraint_limits_even_disjoint_reservations(self):
        p=Profile(3,1.5,1.,6.,10,1,'clustered',cap=40)
        menus={str(i):[(p,float(i+1))] for i in range(4)}
        self.assertEqual(admit(menus,'exact')['admitted'],4)
        tight=admit(menus,'exact',risk_budget=.01,risk_costs={p.key:.006})
        self.assertEqual(tight['admitted'],1)
        self.assertEqual(tight['utility'],4.)
        loose=admit(menus,'exact',risk_budget=.01,risk_costs={p.key:.0025})
        self.assertEqual(loose['admitted'],4)
        self.assertLessEqual(loose['declared_risk_spent'],.01)


class EpisodeTests(unittest.TestCase):
    def test_seed_splits_and_components_are_independent_reproducible_streams(self):
        a=stream(1,'design','plant').random(10)
        np.testing.assert_array_equal(a,stream(1,'design','plant').random(10))
        self.assertFalse(np.array_equal(a,stream(1,'calibration','plant').random(10)))
        self.assertFalse(np.array_equal(a,stream(1,'design','fading').random(10)))

    def test_transition_derivative_includes_nonzero_headway_rate(self):
        p=Profile(5,1.5,.6,6.,20,4,'hopped')
        t=4.;eps=1e-5
        _,dh=gap_reference(t,p,Model())
        numerical=(gap_reference(t+eps,p,Model())[0]-gap_reference(t-eps,p,Model())[0])/(2*eps)
        self.assertAlmostEqual(dh,numerical,places=9)
        self.assertLess(dh,0)

    def test_repeat_covariance_is_psd_and_changes_with_hopping(self):
        p=Profile(5,1.5,1.,6.,20,4,'hopped')
        a=repeat_cholesky(p,ENVIRONMENTS['correlated'])
        b=repeat_cholesky(replace(p,pattern='spread'),ENVIRONMENTS['correlated'])
        for chol in a:
            self.assertGreater(np.linalg.eigvalsh(chol@chol.T).min(),0)
        self.assertFalse(np.allclose(a,b))

    def test_equilibrium_is_preserved_without_communication(self):
        p=Profile(3,1.5,1.5,6.,20,1,'clustered')
        m=replace(Model(),horizon_s=9.,radio_mode='absent',range_noise_sd_m=0.,velocity_noise_sd_mps=0.,
            initial_velocity_error_mps=0.,initial_gap_error_m=0.,initial_acceleration_error_mps2=0.,
            leader_brake_min_mps2=0.,leader_brake_max_mps2=0.)
        v=simulate(p,ENVIRONMENTS['nominal'],1,2,'verification',m)
        self.assertEqual(v['failures'],0)
        self.assertLess(max(v['peak_error_m']),1e-9)
        self.assertEqual(v['episode_packet_loss_fraction'],[1.,1.])

    def test_incomplete_maneuver_is_a_violation_even_when_governor_pauses(self):
        p=Profile(3,1.5,1.,6.,20,1,'clustered')
        m=replace(Model(),horizon_s=9.,radio_mode='absent')
        v=simulate(p,ENVIRONMENTS['nominal'],1,2,'verification',m)
        self.assertEqual(v['completion_failures'],2)
        self.assertEqual(v['episode_violation'],[1,1])

    def test_perfect_radio_control_and_replay_are_explicit(self):
        p=Profile(3,1.5,1.5,6.,20,1,'clustered')
        m=replace(Model(),horizon_s=9.,radio_mode='perfect')
        first=simulate(p,ENVIRONMENTS['nominal'],2,2,'verification',m)
        self.assertEqual(first,simulate(p,ENVIRONMENTS['nominal'],2,2,'verification',m))
        self.assertEqual(first['packet_failures'],0)
        with self.assertRaises(ValueError):simulate(p,ENVIRONMENTS['nominal'],2,2,'verification',replace(m,dt_s=.003))


class PipelineTests(unittest.TestCase):
    def test_test_outcomes_cannot_change_profile_selection(self):
        a=Profile(3,1.5,1.,6.,10,1,'clustered')
        b=Profile(3,1.5,1.,6.,20,4,'hopped')
        records=[]
        for p,failure in [(a,100),(b,0)]:
            for split in ['design','calibration','test']:
                records.append(dict(id=f'{p.key}-{split}',config=dict(profile_id=p.key,environment='nominal',split=split),
                    metrics=dict(failures=failure,episodes=1000,packet_failures=failure,packet_trials_per_episode=1,
                                 peak_error_m=[1.],clearance_failures=0)))
        first=compile_catalog([a,b],records)
        for r in records:
            if r['config']['split']=='test':r['metrics']['failures']=999
        second=compile_catalog([a,b],records)
        self.assertEqual(first['decisions'][0]['selected'],second['decisions'][0]['selected'])
        self.assertNotEqual(first['decisions'][0]['evaluation'],second['decisions'][0]['evaluation'])

    def test_task_assignment_is_complete_disjoint_and_balanced_by_estimate(self):
        tasks=[dict(id=campaign.sha(c)[:20],config=c) for c in campaign.configurations('smoke')]
        bins=campaign.shards(tasks,4)
        assigned=[t['id'] for shard in bins for t in shard]
        self.assertEqual(sorted(assigned),sorted(t['id'] for t in tasks))
        self.assertEqual(len(assigned),len(set(assigned)))
        self.assertEqual(bins,campaign.shards(tasks,4))

    def test_failed_worker_recovers_and_preserves_completed_result(self):
        config=campaign.configurations('smoke')[0]
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(campaign,'ROOT',Path(temp)),patch.object(campaign,'source_fingerprint',return_value={'fixture':True}),\
                 patch.object(campaign,'configurations',return_value=[config]),contextlib.redirect_stdout(io.StringIO()):
                path=campaign.build('smoke')
                with patch('gapslice.guard.simulator.simulate',side_effect=RuntimeError('deliberate worker failure')):
                    self.assertEqual(campaign.worker(path,0,1),1)
                self.assertEqual(campaign.worker(path,0,1),0)
                result=next((Path(temp)/'outputs/guard').glob('guard-smoke-*/results/*.json'))
                before=result.read_bytes()
                with patch('gapslice.guard.simulator.simulate',side_effect=RuntimeError('should be skipped')):
                    self.assertEqual(campaign.worker(path,0,1),0)
                self.assertEqual(result.read_bytes(),before)
                self.assertEqual(json.loads(before)['stage'],'research_prototype_synthetic')


if __name__=='__main__':unittest.main()
