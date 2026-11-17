"""Integrity failures and comparison denominators for exported HPC evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_ojcs_audit import digest, load_campaign, radio_analysis, market_analysis, control_analysis


class ExportIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'source').mkdir()
        (self.root/'source/input.txt').write_text('frozen input')
        config = dict(family='radio', h=1.)
        header = dict(schema=1, stage='synthetic_diagnostic', preset='audit', configs=[config],
                      fingerprint=dict(files={'input.txt': hashlib.sha256(b'frozen input').hexdigest()},
                        runtime={'system':'Different-OS'}, versions={'numpy':'foreign-version'}))
        campaign = 'ojcs-audit-'+digest(header)[:16]
        self.key = digest(config)[:20]
        self.manifest = self.root/'outputs/ojcs/manifests'/f'{campaign}.json'
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps(dict(**header, campaign_id=campaign,
                                                tasks=[dict(id=self.key, config=config)])))
        self.base = self.manifest.parent.parent/campaign
        (self.base/'results').mkdir(parents=True)
        self.record = self.base/'results'/f'{self.key}.json'
        self.record.write_text(json.dumps(dict(id=self.key, config=config, campaign_id=campaign,
            status='complete', stage='synthetic_diagnostic', metrics={'supported':False},
            cpu_s=2., process_peak_rss_mb=10.)))
        self.summary = self.base/'summary.json'
        self.summary.write_text(json.dumps(dict(campaign_id=campaign, expected=1, complete=1,
            failed=0, pending=0, families={'radio':dict(expected=1, complete=1, failed=0, pending=0)},
            diagnostic_cpu_s=2., maximum_observed_process_rss_mb=10.)))

    def test_checks_source_without_requiring_analysts_runtime_to_match(self):
        _, records, _, check = load_campaign(self.manifest, self.root/'source')
        self.assertEqual((len(records), check['source_files_checked']), (1, 1))
        self.assertEqual(check['runtime']['system'], 'Different-OS')

    def test_config_tampering_is_rejected(self):
        r = json.loads(self.record.read_text())
        r['config']['h'] = .5
        self.record.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError, 'identity/status'):
            load_campaign(self.manifest)

    def test_missing_or_failed_records_are_rejected(self):
        self.record.rename(self.record.with_suffix('.failed.json'))
        with self.assertRaisesRegex(ValueError, 'Missing, extra or failed'):
            load_campaign(self.manifest)

    def test_source_drift_is_rejected(self):
        (self.root/'source/input.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            load_campaign(self.manifest, self.root/'source')

    def test_inconsistent_summary_is_rejected(self):
        s = json.loads(self.summary.read_text())
        s['diagnostic_cpu_s'] = 3.
        self.summary.write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError, 'CPU accounting'):
            load_campaign(self.manifest)


class ScientificDenominatorTests(unittest.TestCase):
    def test_unavailable_and_infeasible_radio_cases_do_not_become_savings(self):
        def target(cost):
            p = None if cost is None else dict(prb_slots=cost)
            return dict(inherited_plan_fits_slot=p is not None,
                        capped_plans=dict(power_aware=p, fixed_reference_sinr=p))
        rows=[]
        for i, (a, fixed) in enumerate([(10, 20), (5, None)]):
            rows.append(dict(id=str(i), config=dict(family='radio', cap=51, blocked=False, h=1.+i),
                metrics=dict(supported=True, comparison=dict(descriptor_A=target(a), fixed_9999=target(fixed)))))
        rows.append(dict(id='unavailable', config=dict(family='radio',cap=51,blocked=False,h=.6),
                         metrics=dict(supported=False)))
        d = radio_analysis(rows)
        self.assertEqual((d['supported'], d['unavailable']), (2, 1))
        savings=d['strata'][0]['savings_jointly_feasible']
        self.assertEqual((savings['n'], savings['median']), (1, .5))

    def test_acc_offset_does_not_inflate_primary_market_ratio(self):
        v=dict(exact_reference=dict(proven_optimal=True,incremental_utility=4.,runtime_s=.1),
               incremental_utility=2.,acc_utility=100.,incremental_ratio_to_lp_upper_bound=.4,
               market=dict(utility=102.,feasible=True),fixed=dict(utility=101.,feasible=True),
               menu_build_s=1.,market_s=.01,price_rounds=100)
        d=market_analysis([dict(id='one',config=dict(family='market',tenants=4,contract='A',pool=10,seed=1),metrics=v)])
        self.assertEqual(d['rows'][0]['incremental_ratio_exact'], .5)
        self.assertGreater(d['rows'][0]['total_ratio_exact'], .98)

    def test_reused_seed_is_one_cluster_across_scenarios(self):
        rows=[]
        for seed in [1,2]:
            for h in [1.,1.5]:
                for margin in [0.,-.05]:
                    fraction=.1*seed+(-margin)
                    rows.append(dict(id=f'{seed}-{h}-{margin}',config=dict(family='control',seed=seed,
                        h=h,rho=0.,delivery_margin=margin),metrics=dict(supported=True,
                        growth_events=round(fraction*100),braking_events=100,event_fraction=fraction,
                        mean_square_pulse_gain=.5,finite_platoon_gain_bound=1.05,
                        observed_nonpositive_distance=0,minimum_distance_01_quantile_m=10.)))
        d=control_analysis(rows)
        effect=d['grid_average_margin_effects'][0]['paired_margin_effect']
        self.assertEqual(effect['seed_clusters'],2)
        self.assertAlmostEqual(effect['mean'],.05)


if __name__ == '__main__':
    unittest.main()
