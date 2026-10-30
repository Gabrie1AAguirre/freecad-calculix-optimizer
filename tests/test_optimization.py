import unittest

from optimizer.evaluation import ABOVE, INVALID, OK, OK_CHECK, Iteration
from optimizer.optimization import (STOP_INVALID, STOP_MAX_ITERATIONS, STOP_REQUESTED, BaselineError,
                                    choose_best, optimize)
from optimizer.spreadsheet import Parameter, Settings


def _settings(limit=10.0, max_iterations=30):
    return Settings(parameters=[Parameter("a", 20.0, 1.0, 20.0, "B2"), Parameter("b", 20.0, 1.0, 20.0, "B3")],
                    stress_limit=limit, max_iterations=max_iterations)


class Fake:
    """Fake part: mass = a + b, stress = 1000 / (a * b)."""

    def __init__(self, limit, invalid_if=None):
        self.limit, self.invalid_if, self.calls = limit, invalid_if, []

    def __call__(self, values):
        self.calls.append(dict(values))
        n = len(self.calls)
        if self.invalid_if and self.invalid_if(values):
            return Iteration(n, dict(values), status=INVALID, reason="impossible geometry")
        vm = 1000.0 / (values["a"] * values["b"])
        return Iteration(n, dict(values), von_mises=vm, von_mises_raw=vm, mass_kg=values["a"] + values["b"],
                         status=OK if vm <= self.limit else ABOVE)


def _nothing(*_):
    pass


def _never():
    return False


class TestOptimization(unittest.TestCase):
    def test_finds_light_feasible(self):
        best, hist, _ = optimize(Fake(10.0), _settings(), _nothing, _never)
        self.assertEqual(best.status, OK)
        self.assertLessEqual(best.von_mises, 10.0)
        self.assertLess(best.mass_kg, 30.0)  # starts at 40; the optimum is 20

    def test_respects_limits(self):
        fake = Fake(10.0)
        optimize(fake, _settings(), _nothing, _never)
        for v in fake.calls:
            self.assertTrue(1.0 <= v["a"] <= 20.0 and 1.0 <= v["b"] <= 20.0, v)

    def test_baseline_first(self):
        fake = Fake(10.0)
        optimize(fake, _settings(), _nothing, _never)
        self.assertEqual(fake.calls[0], {"a": 20.0, "b": 20.0})

    def test_steps_not_tiny_when_starting_at_a_bound(self):
        # Initial values at a bound (like corner_radius = minimum): the first steps
        # must be large enough to get out of the mesh noise.
        fake = Fake(10.0)
        optimize(fake, _settings(max_iterations=4), _nothing, _never)
        for v in fake.calls[1:]:
            change = max(abs(v["a"] - 20.0), abs(v["b"] - 20.0)) / 19.0
            self.assertGreaterEqual(change, 0.1, v)

    def test_max_iterations(self):
        _, hist, reason = optimize(Fake(10.0), _settings(max_iterations=5), _nothing, _never)
        self.assertLessEqual(len(hist), 5)
        self.assertEqual(reason, STOP_MAX_ITERATIONS)

    def test_stop_requested(self):
        calls = []

        def stop():
            calls.append(1)
            return len(calls) >= 3
        best, hist, reason = optimize(Fake(10.0), _settings(), _nothing, stop)
        self.assertLessEqual(len(hist), 4)
        self.assertEqual(reason, STOP_REQUESTED)
        self.assertIsNotNone(best)

    def test_on_iteration_reports_best(self):
        notices = []
        optimize(Fake(10.0), _settings(max_iterations=6), lambda it, best: notices.append((it.number, best)), _never)
        self.assertEqual(notices[0], (1, True))
        self.assertEqual(len(notices), 6)

    def test_none_feasible(self):
        best, hist, _ = optimize(Fake(0.1), _settings(limit=0.1, max_iterations=15), _nothing, _never)
        self.assertEqual(best.status, ABOVE)
        self.assertEqual(best.von_mises, min(it.von_mises for it in hist))

    def test_prefers_clean_ok(self):
        to_check = Iteration(1, {}, von_mises=5, mass_kg=1.0, status=OK_CHECK)
        clean = Iteration(2, {}, von_mises=5, mass_kg=2.0, status=OK)
        self.assertIs(choose_best([to_check, clean]), clean)
        self.assertIs(choose_best([to_check]), to_check)

    def test_invalid_does_not_break(self):
        best, hist, _ = optimize(Fake(10.0, invalid_if=lambda v: v["a"] < 12), _settings(), _nothing, _never)
        self.assertIsNotNone(best)
        self.assertNotEqual(best.status, INVALID)

    def test_baseline_already_feasible(self):
        best, hist, _ = optimize(Fake(1e6), _settings(limit=1e6), _nothing, _never)
        self.assertEqual(best.status, OK)
        self.assertLessEqual(best.mass_kg, hist[0].mass_kg)

    def test_invalid_baseline(self):
        fake = Fake(10.0, invalid_if=lambda v: True)
        with self.assertRaises(BaselineError) as ctx:
            optimize(fake, _settings(), _nothing, _never)
        self.assertIn("impossible geometry", str(ctx.exception))
        self.assertEqual(len(fake.calls), 1)

    def test_three_invalid_in_a_row(self):
        fake = Fake(10.0, invalid_if=lambda v: len(fake.calls) > 1)
        best, hist, reason = optimize(fake, _settings(), _nothing, _never)
        self.assertEqual(len(hist), 4)
        self.assertEqual(reason, STOP_INVALID)
        self.assertEqual([it.status for it in hist[1:]], [INVALID] * 3)
        self.assertIs(best, hist[0])


if __name__ == "__main__":
    unittest.main()
