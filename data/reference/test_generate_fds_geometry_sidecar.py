import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from generate_fds_geometry_sidecar import build_sidecar  # noqa: E402


class GenerateFdsGeometrySidecarTest(unittest.TestCase):
    def test_builds_valid_line_sidecar_from_approved_source_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "case.fds").write_text("&MESH IJK=2,2,2, XB=0,1,0,1,0,1 /\n&DEVC ID='D1', QUANTITY='TEMPERATURE', XB=0,0,0,0,0,1 /\n", encoding="utf-8")
            (root / "export.csv").write_text("time_s,probe_id,temperature_C\n0,P1,20\n", encoding="utf-8")
            (root / "crosswalk.csv").write_text("probe_id,source_device_id,mapping_basis,mapping_record_id,mapping_approved\nP1,D1,export-script,record-1,true\n", encoding="utf-8")
            (root / "survey.csv").write_text(
                "source_device_id,support_type,x_m,y_m,z_m,x0_m,y0_m,z0_m,x1_m,y1_m,z1_m,source_geometry_tolerance_m,geometry_uncertainty_m,survey_record_id,notes\n"
                "D1,line,0,0,0.5,0,0,0,0,0,1,0.000001,0.01,survey-1,approved\n",
                encoding="utf-8",
            )
            (root / "case.json").write_text(json.dumps({"coordinate_frame": "fds-frame", "source_fds_coordinate_frame": "fds-frame", "transform_id": "t1"}), encoding="utf-8")
            report = build_sidecar(root / "case.fds", root / "export.csv", root / "crosswalk.csv", root / "survey.csv", root / "case.json", root / "sidecar.csv")
            self.assertEqual(report["status"], "ready")
            with (root / "sidecar.csv").open(encoding="utf-8", newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["source_device_id"], "D1")


if __name__ == "__main__":
    unittest.main()
