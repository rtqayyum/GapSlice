from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from itertools import product
from pathlib import Path
import json
import math
import tempfile
import unittest
import numpy as np

from contractlab.risk import SCALE,tail_upper,upper_units,deployment_allowed
from contractlab.allocation import allocate,check,upper_bound
from contractlab.baselines import ccc,ccc_time_headway_filter,idm
from contractlab.protocol import configuration,design_cells,replay_manifest
from contractlab.common import atomic,sha
from contractlab.campaign import load
from gapslice.certified.profiles import Profile
from dataclasses import asdict


class StatisticalTests(unittest.TestCase):
    def test_directed_binomial_tail_encloses_exact_rational(self):
        for n,k,u in [(17,2,130001),(100,3,70000),(30,0,400000)]:
            exact=sum(Fraction(math.comb(n,j)*u**j*(SCALE-u)**(n-j),SCALE**n) for j in range(k+1))
            bound=Fraction(tail_upper(k,n,u))
            self.assertGreaterEqual(bound,exact)
            self.assertLess(float(bound-exact),1e-50)

    def test_label_is_monotone_and_has_statistical_not_fixed_floor(self):
        a=upper_units(0,65536,288);b=upper_units(1,65536,288)
        self.assertLessEqual(a,b);self.assertLess(a,10000/16)
        self.assertLessEqual(tail_upper(0,65536,a),Decimal(1)/Decimal(40*288))
        self.assertGreater(upper_units(0,100,288),a)
        self.assertEqual(upper_units(100,100,1),SCALE)

    def test_contract_rejects_changed_context_horizon_or_source(self):
        c=dict(context='nominal',horizon_s=40,profile=dict(payload_bytes=300),source_sha256='abc',qualified=True)
        self.assertTrue(deployment_allowed(c,'nominal',40,300,'abc'))
        for args in [('blocked',40,300,'abc'),('nominal',80,300,'abc'),('nominal',40,600,'abc'),('nominal',40,300,'bad')]:
            self.assertFalse(deployment_allowed(c,*args))


def option(i,risk,value,radio=False):
    p=Profile(n_trucks=3,h_target=1.2,cap=51,prbs=20 if radio else 0,copies=1 if radio else 0,
              pattern='hopped' if radio else 'none',layout='serial' if radio else 'none')
    return dict(id=i,profile=asdict(p),risk_units=risk,benefit_microseconds=value)


class AllocationTests(unittest.TestCase):
    def test_integer_relaxation_bounds_exhaustive_small_problem(self):
        menus={'a':[option('x',310,13),option('y',230,9,True)],'b':[option('z',330,15)]}
        exact=max(sum(c['benefit_microseconds'] for c in picks if c) for picks in product([None,*menus['a']],[None,*menus['b']]) if sum(c['risk_units'] for c in picks if c)<=560)
        upper=upper_bound(menus,560);self.assertGreaterEqual(upper,exact)
        result=allocate(menus,560,51,time_limit=2)
        self.assertEqual(result['benefit_microseconds'],exact)

    def test_fine_costs_allow_more_than_sixteen_no_radio_tenants(self):
        menus={str(i):[option(str(i),300,10)] for i in range(32)}
        result=allocate(menus,10000,51,time_limit=2)
        self.assertEqual(result['admitted'],32)

    def test_checker_rejects_duplicate_conflict_and_risk_excess(self):
        c=option('x',6000,13,True);x=dict(tenant='a',contract=c,offset=0)
        with self.assertRaises(RuntimeError):check([x,x],10000,51)
        with self.assertRaises(RuntimeError):check([x,dict(x,tenant='b')],20000,51)
        with self.assertRaises(RuntimeError):check([x],5000,51)

    def test_union_retains_valid_baseline_incumbent(self):
        menus={'a':[option('x',310,13),option('y',230,9,True)],'b':[option('z',330,15)]}
        baseline=allocate({o:[m[0]] for o,m in menus.items()},560,51,time_limit=2)
        result=allocate(menus,560,51,method='greedy',incumbents=[baseline['allocation']])
        self.assertGreaterEqual(result['benefit_microseconds'],baseline['benefit_microseconds'])


class ProtocolTests(unittest.TestCase):
    def test_fresh_splits_and_controller_pairing(self):
        cfg=configuration('smoke');cells=design_cells(cfg)
        a=replay_manifest('calibration',cells,cfg);b=replay_manifest('test',cells,cfg)
        self.assertNotEqual(a['tasks'][0]['seed'],b['tasks'][0]['seed'])
        self.assertEqual(len({t['seed'] for t in a['tasks'] if t['offset']==0}),1)
        self.assertTrue(all(c['model']['data_namespace'].startswith('contract-framework-fresh') for c in cells.values()))

    def test_required_result_hashes_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);task=dict(id='a',cell='c');raw=folder/'results/a.npz';raw.parent.mkdir();raw.write_bytes(b'bad')
            atomic(folder/'results/a.json',dict(task_sha256=sha(task),raw='a.npz',raw_sha256='incorrect'))
            with self.assertRaises(RuntimeError):load(folder,task)


class PublishedEquationTests(unittest.TestCase):
    def test_native_ccc_table_one_and_cbf_inequality(self):
        self.assertAlmostEqual(float(ccc(30,15,15,0,.6,A=.4,B=.6,C=0,standstill=5,speed_limit=15)),0)
        for d,v,vl in [(30,15,15),(20,12,8),(5,2,0)]:
            u=float(ccc_time_headway_filter(2,d,v,vl));h=(d-1)/1.67-v
            self.assertGreaterEqual((vl-v)/1.67-u+h,-1e-12)

    def test_idm_brakes_more_for_approaching_leader(self):
        self.assertLess(float(idm(30,20,10,1.,30)),float(idm(30,20,20,1.,30)))

if __name__=='__main__':unittest.main()
