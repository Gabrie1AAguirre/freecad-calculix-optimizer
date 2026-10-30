import unittest

from optimizer.face_tracking import FaceSignature, capture_signatures, compare_signatures
from optimizer.model import find_model
from optimizer.spreadsheet import apply_values, read_settings
from tests.util import L_EXAMPLE, open_copy


def _diagonal(m):
    return m.body.Shape.BoundBox.DiagonalLength


class TestFaceTracking(unittest.TestCase):
    def setUp(self):
        self.doc = open_copy(L_EXAMPLE, self)
        self.m = find_model(self.doc)
        self.before = capture_signatures(self.m)

    def test_stable_signature(self):
        apply_values(self.doc, read_settings(self.doc), {"vertical_thickness": 40, "corner_radius": 12})
        self.doc.recompute()
        self.assertEqual(compare_signatures(self.before, capture_signatures(self.m), _diagonal(self.m)), [])

    def test_signature_detects_swap(self):
        force = self.doc.getObject("ConstraintForce")
        obj, _ = force.References[0]
        force.References = [(obj, "Face2")]
        self.doc.recompute()
        problems = compare_signatures(self.before, capture_signatures(self.m), _diagonal(self.m))
        self.assertTrue(problems)
        self.assertIn("ConstraintForce", " ".join(problems))

    def test_missing_face(self):
        force = self.doc.getObject("ConstraintForce")
        obj, _ = force.References[0]
        force.References = [(obj, "Face99")]
        problems = compare_signatures(self.before, capture_signatures(self.m), _diagonal(self.m))
        self.assertTrue(problems)
        self.assertIn("Face99", " ".join(problems))


class TestNeighborFace(unittest.TestCase):
    """Swap to a neighbor face on the same plane and of similar size: same normal,
    close center and area of the same order pass the limits — but another face matches better."""

    BEFORE = {"ConstraintForce": [FaceSignature("Face13", 400.0, (30.0, -10.0, 220.0), (1.0, 0.0, 0.0))]}

    def test_detects_swap_to_similar_neighbor(self):
        original = FaceSignature("Face13", 400.0, (30.0, -10.0, 220.0), (1.0, 0.0, 0.0))
        neighbor = FaceSignature("Face14", 200.0, (30.0, -10.0, 235.0), (1.0, 0.0, 0.0), alternatives=[original])
        problems = compare_signatures(self.BEFORE, {"ConstraintForce": [neighbor]}, 290.0)
        self.assertTrue(problems)
        self.assertIn("Face13", " ".join(problems))

    def test_face_that_only_moved_stays_valid(self):
        far = FaceSignature("Face10", 3580.0, (40.0, -10.0, 120.0), (1.0, 0.0, 0.0))
        moved = FaceSignature("Face13", 400.0, (40.0, -10.0, 220.0), (1.0, 0.0, 0.0), alternatives=[far])
        self.assertEqual(compare_signatures(self.BEFORE, {"ConstraintForce": [moved]}, 290.0), [])


if __name__ == "__main__":
    unittest.main()
