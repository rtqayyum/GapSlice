"""Physical invariants and adversarial checks for revision prototypes."""
import math
import unittest

from gapslice.revision.radio_budget import RadioBudget
from gapslice.revision.slot_schedule import Job, Placement, pack, validate


class RadioTests(unittest.TestCase):
    def test_noise_scales_with_occupied_bandwidth(self):
        radio = RadioBudget(106)
        self.assertAlmostEqual(radio.total_noise_dbm(40) - radio.total_noise_dbm(20),
                               10 * math.log10(2), places=12)

    def test_noise_limited_sinr_falls_with_bandwidth(self):
        radio = RadioBudget(106)
        self.assertAlmostEqual(radio.sinr_db(100, [], 20) - radio.sinr_db(100, [], 40),
                               10 * math.log10(2), places=12)

    def test_power_never_increases_to_preserve_sinr(self):
        radio = RadioBudget(106)
        self.assertLess(radio.sinr_db(100, [110, 110], 100),
                        radio.sinr_db(100, [110, 110], 10))
        self.assertEqual(radio.tx_power_dbm, 23)

    def test_bandwidth_and_deadline(self):
        radio = RadioBudget(51)
        self.assertEqual(radio.deadline_slots, 20)
        self.assertEqual(radio.resource_upper_bound, 1020)
        with self.assertRaises(ValueError):
            radio.total_noise_dbm(52)


class SchedulingTests(unittest.TestCase):
    def test_half_duplex_prevents_adjacent_chain_links(self):
        jobs = [Job('a', 'p0', 'v0', 'v1', 10, 0, 2),
                Job('b', 'p1', 'v1', 'v2', 10, 0, 2)]
        placed, left = pack(jobs, 51)
        self.assertFalse(left)
        self.assertNotEqual(placed[0].slot, placed[1].slot)
        self.assertFalse(validate(placed, 51, jobs))

    def test_checker_detects_illegal_half_duplex(self):
        a = Job('a', 'p0', 'v0', 'v1', 10, 0, 1)
        b = Job('b', 'p1', 'v1', 'v2', 10, 0, 1)
        errors = validate([Placement(a, 0, 0), Placement(b, 0, 10)], 51)
        self.assertIn('radio conflict: b', errors)

    def test_checker_detects_overlap_and_late_missing_copies(self):
        a = Job('a', 'p0', 'a', 'b', 30, 0, 1)
        b = Job('b', 'p1', 'c', 'd', 30, 0, 1)
        c = Job('c', 'p2', 'e', 'f', 10, 0, 1)
        errors = validate([Placement(a, 1, 0), Placement(b, 1, 20)], 51, [a, b, c])
        self.assertIn('deadline/release: a', errors)
        self.assertIn('overlap: b', errors)
        self.assertIn('missing job: c', errors)

    def test_many_resources_do_not_override_deadline(self):
        jobs = [Job(str(i), 'p', 'v0', 'v1', 5, 0, 2) for i in range(3)]
        placed, left = pack(jobs, 106)
        self.assertEqual(len(placed), 2)
        self.assertEqual(len(left), 1)

    def test_independent_links_share_slot_on_disjoint_prbs(self):
        jobs = [Job('a', 'p0', 'a', 'b', 20, 0, 1),
                Job('b', 'p1', 'c', 'd', 20, 0, 1)]
        placed, left = pack(jobs, 51)
        self.assertFalse(left)
        self.assertEqual([p.slot for p in placed], [0, 0])
        self.assertFalse(validate(placed, 51, jobs))


if __name__ == '__main__':
    unittest.main()
