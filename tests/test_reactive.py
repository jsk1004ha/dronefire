import json
import tempfile
import unittest
from pathlib import Path

from firelab.reactive import (
    _pulse_ramp,
    build_reactive_case,
    capabilities,
    default_reactive_conditions,
    default_reactive_config,
)


class ReactiveCaseTests(unittest.TestCase):
    def test_default_design_has_36_unique_conditions(self):
        conditions = default_reactive_conditions()
        self.assertEqual(len(conditions), 36)
        self.assertEqual(len({item["id"] for item in conditions}), 36)
        self.assertEqual(sum(item["mode"] == "control" for item in conditions), 1)
        self.assertEqual(sum(item["mode"] == "single" for item in conditions), 5)
        self.assertEqual(sum(item["mode"] == "simultaneous" for item in conditions), 10)
        self.assertEqual(sum(item["mode"] == "sequential" for item in conditions), 20)

    def test_capabilities_gate_chemical_and_ehd_methods(self):
        result = capabilities()
        self.assertEqual(result["M1"]["status"], "ready")
        self.assertEqual(result["M3"]["status"], "ready")
        self.assertEqual(result["M4"]["status"], "needs_model")
        self.assertEqual(result["M5"]["status"], "needs_model")
        self.assertIn("agent_name", result["M4"]["missing"])

    def test_supported_case_writes_native_input_without_forced_hrr_curve(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = build_reactive_case(None, "S_M3", temporary)
            self.assertEqual(manifest["status"], "ready")
            text = Path(manifest["input_path"]).read_text(encoding="utf-8")
            self.assertIn("PARTICLE_MASS_FLUX", text)
            self.assertIn("EXTINCTION_MODEL='EXTINCTION 2'", text)
            self.assertNotIn("SUPPRESSION_FACTOR", text)
            self.assertTrue((Path(temporary) / "case_manifest.json").is_file())

    def test_blocked_component_never_receives_surrogate_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = build_reactive_case(None, "S_M4", temporary)
            self.assertEqual(manifest["status"], "needs_model")
            self.assertIsNone(manifest["input_path"])
            payload = json.loads((Path(temporary) / "needs_model.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["unsupported_methods"], ["M4"])

    def test_sequence_records_full_dose_and_distinct_schedule(self):
        item = next(value for value in default_reactive_conditions() if value["id"] == "SEQ_M1_THEN_M3")
        self.assertEqual(item["dose_fraction"], {"M1": 1.0, "M3": 1.0})
        self.assertEqual(item["schedule"]["M1"]["duration_s"], 2.0)
        self.assertEqual(item["schedule"]["M3"]["start_s"], 8.0)

    def test_invalid_out_of_window_schedule_is_rejected(self):
        item = next(value for value in default_reactive_conditions() if value["id"] == "S_M1")
        item["schedule"]["M1"]["start_s"] = 5.0
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_reactive_case(default_reactive_config(), item, temporary)

    def test_pulsed_nozzle_uses_declared_pulse_width(self):
        ramp = "\n".join(_pulse_ramp("jet", 6.0, 2.0, cycles=2, period=1.0, pulse_width=.05))
        self.assertIn("T=6.05, F=1", ramp)
        self.assertIn("T=7.05, F=1", ramp)
        self.assertNotIn("T=6.5, F=1", ramp)

    def test_checked_in_default_config_is_accepted(self):
        config_path = Path(__file__).parents[1] / "configs" / "reactive_default.json"
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(build_reactive_case(loaded, "C0", temporary)["status"], "ready")

    def test_source_patches_are_always_present_and_never_overlap_full_open_face(self):
        with tempfile.TemporaryDirectory() as temporary:
            c0 = build_reactive_case(None, "C0", Path(temporary) / "c0")
            m3 = build_reactive_case(None, "S_M3", Path(temporary) / "m3")
            c0_text = Path(c0["input_path"]).read_text(encoding="utf-8")
            m3_text = Path(m3["input_path"]).read_text(encoding="utf-8")
            c0_xmin_vents = [line for line in c0_text.splitlines() if line.startswith("&VENT XB=0,0")]
            m3_xmin_vents = [line for line in m3_text.splitlines() if line.startswith("&VENT XB=0,0")]
            self.assertEqual(c0_xmin_vents, m3_xmin_vents)
            self.assertNotIn("XB=0,0,-0.6,0.6,0,1, SURF_ID='OPEN'", c0_text)
            for method in ("M1", "M2", "M3"):
                self.assertIn(f"SURF_ID='SRC_{method}'", c0_text)

    def test_m3_carrier_and_particles_share_the_off_on_ramp(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = build_reactive_case(None, "S_M3", temporary)
            text = Path(manifest["input_path"]).read_text(encoding="utf-8")
            source = next(line for line in text.splitlines() if line.startswith("&SURF ID='SRC_M3'"))
            self.assertIn("RAMP_V='R_M3_S_M3'", source)
            self.assertIn("RAMP_PART='R_M3_S_M3'", source)
            self.assertEqual(manifest["intervention_activation"]["status"], "unverified")
            self.assertEqual(manifest["intervention_activation"]["method_windows_s"]["M3"], [6.0, 10.0])
            self.assertEqual(manifest["intervention_activation"]["thresholds"]["M3"]["source_m3_droplet_volume_fraction"]["value"], 1.0e-12)

    def test_mesh_and_domain_changes_cannot_silently_unresolve_sources(self):
        config = default_reactive_config()
        config["case"]["mesh_cell_m"] = .1
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_reactive_case(config, "C0", temporary)


if __name__ == "__main__":
    unittest.main()
