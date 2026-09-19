import json
import shutil
import tempfile
import unittest
from pathlib import Path

from firelab.openfoam_fields import (
    OpenFOAMFieldError,
    export_openfoam_taylor_green,
    read_openfoam_taylor_green,
)


ROOT = Path(__file__).parents[1]
ACTUAL = ROOT / "runs" / "openfoam_v2412_taylor_green_spatial" / "mesh_20"


class OpenFOAMFieldTests(unittest.TestCase):
    def setUp(self):
        if not ACTUAL.is_dir():
            self.skipTest("native Taylor-Green case is not present")

    def test_actual_mesh_is_proven_structured_and_exactly_counted(self):
        result = read_openfoam_taylor_green(ACTUAL)
        field = result["fields"][0]
        self.assertEqual(result["resolution"], 20)
        self.assertEqual(field["geometry"]["shape_kji"], [1, 20, 20])
        self.assertEqual(field["geometry"]["topology"], "plane")
        self.assertEqual(field["geometry"]["axes_m"]["z"], [0.05])
        proof = field["geometry"]["structured_geometry_proof"]
        self.assertEqual(proof["cell_count"], 400)
        self.assertTrue(proof["all_cells_axis_aligned_hexahedra"])
        self.assertTrue(proof["complete_cartesian_cell_coverage"])

    def test_actual_time_directories_and_velocity_counts_are_preserved(self):
        field = read_openfoam_taylor_green(ACTUAL)["fields"][0]
        self.assertEqual([frame["time_s"] for frame in field["frames"]], [0.0, 0.2])
        self.assertTrue(all(len(frame["values"]) == 400 for frame in field["frames"]))
        self.assertTrue(all(len(frame["provenance"]["source_sha256"]) == 64 for frame in field["frames"]))
        self.assertAlmostEqual(field["frames"][-1]["maximum"], 0.9736735681657238)

    def test_export_matches_shared_field_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "field.json"
            result = export_openfoam_taylor_green(ACTUAL, output)
            loaded = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(loaded["field_count"], result["field_count"])
            field = loaded["fields"][0]
            self.assertIn("axes_m", field["geometry"])
            self.assertIn("shape_kji", field["geometry"])
            self.assertIn("source_path", field["provenance"])
            self.assertIn("source_sha256", field["provenance"])
            self.assertEqual(len(field["provenance"]["case_configuration_sources"]), 5)

    def test_binary_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "case"
            shutil.copytree(ACTUAL, copied)
            points = copied / "constant" / "polyMesh" / "points"
            text = points.read_text(encoding="utf-8").replace("format      ascii;", "format      binary;", 1)
            points.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(OpenFOAMFieldError, "ASCII"):
                read_openfoam_taylor_green(copied)

    def test_non_rectilinear_point_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "case"
            shutil.copytree(ACTUAL, copied)
            points = copied / "constant" / "polyMesh" / "points"
            text = points.read_text(encoding="utf-8").replace("(0 0 0)", "(0.01 0.02 0)", 1)
            points.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(OpenFOAMFieldError, "Cartesian product"):
                read_openfoam_taylor_green(copied)


if __name__ == "__main__":
    unittest.main()
