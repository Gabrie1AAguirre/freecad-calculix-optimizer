import csv
import os
import shutil
import tempfile
import unittest

from optimizer.evaluation import ABOVE, INVALID, OK, OK_CHECK, Iteration
from optimizer.outputs import History, make_chart, summary, terminal_header, terminal_line

ALIASES = ["corner_radius", "vertical_thickness"]
BASE = Iteration(1, {"corner_radius": 1.0, "vertical_thickness": 30.0}, von_mises=509.2, von_mises_raw=509.2,
                 location=(30.0, -10.0, 31.9), mass_kg=1.79, status=ABOVE)
GOOD = Iteration(3, {"corner_radius": 14.0, "vertical_thickness": 35.0}, von_mises=247.0, von_mises_raw=300.0,
                 location=(40.0, -10.0, 45.0), mass_kg=1.95, status=OK)
BAD = Iteration(4, {"corner_radius": 20.0, "vertical_thickness": 45.0}, status=INVALID, reason="mesh failed")


class TestOutputs(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_csv(self):
        path = os.path.join(self.folder, "history.csv")
        h = History(path, ALIASES)
        h.add(BASE)
        with open(path, encoding="utf-8-sig") as f:  # already written at each row
            self.assertEqual(len(f.read().strip().splitlines()), 2)
        h.add(BAD)
        with open(path, "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["iteration", "corner_radius", "vertical_thickness", "von_mises_mpa",
                                   "von_mises_raw_mpa", "max_location", "mass_kg", "status", "reason"])
        self.assertEqual(rows[1][:4], ["1", "1", "30", "509.2"])
        self.assertEqual(rows[1][7], "above limit")
        self.assertEqual(rows[2][3], "")
        self.assertEqual(rows[2][8], "mesh failed")

    def test_terminal_line(self):
        line = terminal_line(BASE, ALIASES, is_best=False)
        self.assertIn("509 MPa", line)
        self.assertIn("1.79 kg", line)
        self.assertIn("above limit", line)
        self.assertIn("OK ✓ best so far", terminal_line(GOOD, ALIASES, is_best=True))
        self.assertIn("mesh failed", terminal_line(BAD, ALIASES, is_best=False))

    def test_header_aligned(self):
        header = terminal_header(ALIASES)
        line = terminal_line(BASE, ALIASES, is_best=False)
        self.assertEqual(header.index("VonMises_max"), line.index("509 MPa") - (len("VonMises_max") - len("509 MPa")))

    def test_chart(self):
        path = os.path.join(self.folder, "chart.png")
        make_chart([BASE, GOOD, BAD], 250.0, path)
        self.assertGreater(os.path.getsize(path), 1000)

    def test_summary(self):
        text = summary(BASE, GOOD, 250.0)
        self.assertIn("reached", text)
        self.assertNotIn("did not reach", text)
        self.assertIn("+8.9%", text)  # mass 1.79 → 1.95
        not_reached = summary(BASE, BASE, 250.0)
        self.assertIn("did not reach", not_reached)
        to_check = Iteration(5, GOOD.values, von_mises=240, mass_kg=1.9, status=OK_CHECK, reason="peak")
        self.assertIn("checking", summary(BASE, to_check, 250.0))


if __name__ == "__main__":
    unittest.main()
