import math
import unittest

from optimizer.stress import measure_stress


def _distance_x(p):
    return p[0]


class TestStress(unittest.TestCase):
    def test_ignores_peak_in_zone(self):
        coords = [(1, 0, 0), (50, 0, 0), (60, 0, 0)]
        m = measure_stress(coords, [900, 300, 100], _distance_x, 10, 5, 250)
        self.assertEqual(m.filtered_max, 300)
        self.assertEqual(m.filtered_location, (50, 0, 0))
        self.assertEqual(m.raw_max, 900)
        self.assertEqual(m.raw_location, (1, 0, 0))
        self.assertEqual(m.max_in_zone, 900)
        self.assertFalse(m.at_edge)

    def test_zone_edge(self):
        coords = [(12, 0, 0), (60, 0, 0)]
        self.assertTrue(measure_stress(coords, [300, 100], _distance_x, 10, 5, 250).at_edge)
        coords = [(40, 0, 0), (60, 0, 0)]
        self.assertFalse(measure_stress(coords, [300, 100], _distance_x, 10, 5, 250).at_edge)

    def test_no_exclusion(self):
        coords = [(1, 0, 0), (50, 0, 0)]
        m = measure_stress(coords, [900, 300], lambda p: math.inf, 10, 5, 250)
        self.assertEqual(m.filtered_max, 900)
        self.assertEqual(m.raw_max, 900)
        self.assertEqual(m.max_in_zone, 0)

    def test_distance_only_computed_at_the_top(self):
        calls = []

        def dist(p):
            calls.append(p)
            return p[0]
        coords = [(i, 0, 0) for i in range(1000)]
        vm = [float(i) for i in range(1000)]
        measure_stress(coords, vm, dist, 10, 5, 250)
        self.assertLessEqual(len(calls), 5)


if __name__ == "__main__":
    unittest.main()
