import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from adapter_contract import ArtifactInspection, canonicalize, gate_results, inspect_coordinate_transform_registry, inspect_fds_input, inspect_fds_output, inspect_fds_probe_geometry_sidecar, inspect_openfoam_case, inspect_time_alignment_ledger  # noqa: E402


class AdapterContractTest(unittest.TestCase):
    def test_celsius_and_percent_are_explicitly_converted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "sensor.csv"
            csv_path.write_text("time_s,x_m,y_m,z_m,temperature_C,oxygen_pct\n0,0,0,0,20,20.9\n", encoding="utf-8")
            inspection = ArtifactInspection("sensor", "measurement_csv", str(csv_path), "hash", 1, [], "ready", [])
            spec = {"path": str(csv_path), "artifact_id": "sensor", "probe_geometry": {}}
            case = {"project_id": "p", "case_id": "c", "run_id": "r", "coordinate_frame": "rhs-z-up", "transform_id": "t1", "time_basis": "event-clock"}
            rows = canonicalize(spec, inspection, case)
            values = {row["field_id"]: row for row in rows}
            self.assertAlmostEqual(values["temperature_K"]["scalar_value"], 293.15)
            self.assertAlmostEqual(values["oxygen_mole_fraction"]["scalar_value"], 0.209)
            self.assertEqual(values["temperature_K"]["unit_conversion"], "K = degC + 273.15")

    def test_missing_geometry_blocks_spatial_gate(self):
        left = ArtifactInspection("left", "fds", "", "a", 1, [], "ready", [])
        right = ArtifactInspection("right", "of", "", "b", 1, [], "ready", [])
        base = {"field_id": "temperature_K", "analysis_time_s": 0, "coordinate_frame": "rhs", "transform_id": "t", "support_type": "point"}
        left_rows = [{**base, "support_type": None}]
        right_rows = [base]
        gates = gate_results(left, right, left_rows, right_rows, 1.0)
        self.assertEqual(gates[2].status, "blocked")
        self.assertEqual(gates[4].status, "blocked")

    def test_fds_input_inspector_extracts_declared_mesh(self):
        fds_path = Path("/home/ubuntu/aeris_review/external/AERIS_Research_External_AI_Review_2026-08-26/research_sources/steckler_benchmark/Steckler_010.fds")
        report = inspect_fds_input(fds_path)
        self.assertEqual(report["mesh"]["ijk"], [72, 56, 44])
        self.assertEqual(report["mesh"]["cell_count"], 177408)
        self.assertGreater(report["device_count"], 0)

    def test_openfoam_inspector_detects_native_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "constant" / "polyMesh").mkdir(parents=True)
            (root / "system").mkdir()
            (root / "system" / "controlDict").write_text("application pimpleFoam;", encoding="utf-8")
            (root / "system" / "sampleDict").write_text("sets ();", encoding="utf-8")
            (root / "0").mkdir()
            for field in ("U", "p", "T"):
                (root / "0" / field).write_text("FoamFile{}", encoding="utf-8")
            (root / "log.pimpleFoam").write_text("solver log", encoding="utf-8")
            report = inspect_openfoam_case(root)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["fields"], ["T", "U", "p"])

    def test_fds_output_inspector_records_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "case.out"
            output_path.write_text("Time: 0.0\nTime: 10.0\nWARNING: test diagnostic\nSTOP: FDS completed successfully (CHID: case)\n", encoding="utf-8")
            report = inspect_fds_output(output_path)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["time_records"], [0.0, 10.0])
            self.assertEqual(report["warning_count"], 1)

    def test_fds_geometry_sidecar_requires_real_crosswalk_and_coordinates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar_path = Path(temp_dir) / "geometry.csv"
            sidecar_path.write_text(
                "probe_id,source_device_id,support_type,x_m,y_m,z_m,coordinate_frame,transform_id,geometry_uncertainty_m,source_fds_sha256\n"
                "O-01,TC_Room,point,1.0,2.0,3.0,rhs,t1,0.01,input-hash\n",
                encoding="utf-8",
            )
            fds_report = {"sha256": "input-hash", "devices": [{"id": "'TC_Room'"}]}
            report = inspect_fds_probe_geometry_sidecar(sidecar_path, {"O-01"}, fds_report, "rhs", "t1")
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["probe_geometry"]["O-01"]["source_device_id"], "TC_Room")

    def test_fds_line_geometry_sidecar_matches_devc_xb(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar_path = Path(temp_dir) / "line_geometry.csv"
            sidecar_path.write_text(
                "probe_id,source_device_id,support_type,x_m,y_m,z_m,x0_m,y0_m,z0_m,x1_m,y1_m,z1_m,source_geometry_tolerance_m,coordinate_frame,transform_id,geometry_uncertainty_m,source_fds_sha256\n"
                "O-01,TC_Room,line,0.5,2.5,4.5,0,2,4,1,3,5,0.000001,rhs,t1,0.01,input-hash\n",
                encoding="utf-8",
            )
            fds_report = {"sha256": "input-hash", "devices": [{"id": "'TC_Room'", "support": "line", "xb": "0,1,2,3,4,5"}]}
            report = inspect_fds_probe_geometry_sidecar(sidecar_path, {"O-01"}, fds_report, "rhs", "t1")
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["probe_geometry"]["O-01"]["support_type"], "line")

    def test_transform_and_time_ledgers_require_explicit_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transform = root / "transform.csv"
            transform.write_text(
                "control_point_id,source_frame,target_frame,transform_id,x_source_m,y_source_m,z_source_m,x_target_m,y_target_m,z_target_m,residual_m,source_record_id\n"
                + "\n".join(f"P{i},survey,rhs,t1,{i},0,0,{i},0,0,0.001,record-{i}" for i in range(6)) + "\n",
                encoding="utf-8",
            )
            ledger = root / "time.csv"
            ledger.write_text(
                "clock_id,native_time_basis,analysis_time_basis,reference_event_id,offset_s,drift_s_per_s,fit_residual_s,method,source_file_sha256\n"
                "fds,native,event,evt-1,0,0,0.01,reference-event,hash-a\n",
                encoding="utf-8",
            )
            self.assertEqual(inspect_coordinate_transform_registry(transform, "rhs", "t1")["status"], "ready")
            self.assertEqual(inspect_time_alignment_ledger(ledger, {"fds"})["status"], "ready")


if __name__ == "__main__":
    unittest.main()
