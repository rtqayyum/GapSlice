import itertools
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.stats import binom

from gapslice.certified.safety import Bounds,Shield,ensure_tables,ego_envelope,predecessor_envelope
from gapslice.certified.profiles import Profile,catalog,allocate
from gapslice.certified.risk import critical_count,qualify,benefit_lower,nominal_certificate
from gapslice.certified.observer import Observer
from gapslice.certified.verification import verify
from gapslice.certified.simulator import Policy,Model,simulate,rng
from gapslice.guard.simulator import ENVIRONMENTS


class CertifiedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.tables=ensure_tables(Path(cls.temp.name));cls.shield=Shield(cls.tables)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_independent_numerical_verifier(self):
        self.assertEqual(verify(self.tables,32)['status'],'passed')

    def test_factorized_envelope_dominates_direct_recurrence(self):
        random=np.random.default_rng(51);b=Bounds()
        v=random.uniform(0,40,25);a=random.choice(self.shield.acceleration,25);u=random.choice(self.shield.command,25)
        pv=random.uniform(0,40,25);pa=random.choice(self.shield.acceleration,25)
        pred=np.stack(list(predecessor_envelope(pv,pa,b)),axis=1)
        for prefix in [False,True]:
            ego=np.stack(list(ego_envelope(v,a,u,b,prefix)),axis=1)
            reference=2+np.maximum(0,np.max(ego[:,1:]-pred,axis=1))
            actual,_=self.shield.required_clearance(v,a,u,pv,pa,prefix)
            self.assertTrue(np.all(actual>=reference-2e-9))

    def test_fail_closed_and_monotonic_state_rounding(self):
        invalid,valid=self.shield.required_clearance([41,np.nan],0,0,20,0)
        self.assertTrue(np.isinf(invalid).all());self.assertFalse(valid.any())
        x=np.arange(10,30,.2);req,_=self.shield.required_clearance(x,.03,.01,20,-.13)
        self.assertTrue(np.all(np.diff(req)>=-1e-8))
        with self.assertRaises(ValueError):Bounds(actual_jerk_bound=8).check()

    def test_cyclic_geometry_and_serial_width(self):
        for p in catalog(n=5,h=.6,phases=(0,8)):p.check()
        p=Profile(layout='serial',prbs=40,phase=8);p.check()
        self.assertEqual(p.width,50)  # frequency hopping uses the spare 10 PRBs
        self.assertIn(2,p.release_ticks())
        with self.assertRaises(ValueError):Profile(n_trucks=7,layout='serial',copies=4).check()
        with self.assertRaises(ValueError):Profile(prbs=40).check()

    def test_integer_allocation_bound_and_no_radio_outside_option(self):
        p=Profile(prbs=0,copies=0,layout='none',pattern='none');p.check()
        menus={str(i):[(p,100+i)] for i in range(5)}
        result=allocate(menus,{p.key:4},method='exact')
        self.assertEqual(result['admitted'],4);self.assertEqual(result['benefit_microseconds'],410)
        self.assertTrue(result['independently_optimal']);self.assertEqual(result['checked_jobs'],0)

    def test_exact_binomial_thresholds(self):
        for n,u,m in itertools.product([64,512,2048],[1,4,16],[1,17]):
            k=critical_count(n,u,m)
            if k>=0:self.assertLessEqual(binom.cdf(k,n,u/1600),1/(25*m)*(1+1e-10))
            self.assertGreater(binom.cdf(k+1,n,u/1600),1/(25*m)*(1-1e-10))
        self.assertEqual(qualify(0,8,100),[])
        self.assertEqual(benefit_lower(0,100,1,10),0)
        self.assertLess(benefit_lower(90,100,1,10),.9)

    def test_nonzero_radio_packing_and_loose_independent_bound(self):
        a=Profile(n_trucks=3,layout='serial',prbs=40,copies=2,phase=0)
        b=Profile(n_trucks=3,layout='serial',prbs=40,copies=2,phase=2)
        menus={str(i):[(a,100),(b,100)] for i in range(3)}
        r=allocate(menus,{a.key:1,b.key:1},method='exact')
        self.assertEqual(r['admitted'],2)
        self.assertGreater(r['checked_jobs'],0)
        self.assertEqual(r['independent_integer_upper_bound'],300)
        self.assertFalse(r['independently_optimal'])
        self.assertAlmostEqual(r['guaranteed_catalog_ratio'],2/3)

    def test_observer_bound_with_upward_stop_jump(self):
        b=Bounds();o=Observer((1,),b);random=np.random.default_rng(71)
        velocity=20.;accel=0.
        for k in range(400):
            nexta=max(-6,accel-.09) if k<200 else 0.
            velocity+=.01*(accel+nexta)/2;accel=nexta
            y=np.array([velocity+random.uniform(-.05,.05)])
            self.assertLessEqual(o.update(y)[0],accel+1e-9)

    def test_lyapunov_witness_and_split_separation(self):
        for kp,kd in [(.4,1.4),(.8,1.8),(1.2,2.2)]:self.assertLess(nominal_certificate(kp,kd)['residual'],1e-12)
        a=rng(1,'design','eta','x').random(5);b=rng(1,'test','eta','x').random(5)
        self.assertFalse(np.array_equal(a,b))

    def test_replay_entry_and_true_zero_radio(self):
        p=Profile(n_trucks=3,prbs=0,copies=0,layout='none',pattern='none')
        x=simulate(p,Policy(controller='radar'),ENVIRONMENTS['blocked'],19,2,'verification',self.shield)
        self.assertEqual(x['packet_trials_per_episode'],0)
        self.assertEqual(x['safety_certificate_breaches'],0)
        self.assertEqual(x['initial_uncertified'],0)
        self.assertTrue(np.all(np.asarray(x['minimum_clearance_m'])>=2))
