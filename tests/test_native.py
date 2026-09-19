import json
import tempfile
import unittest
from pathlib import Path

from firelab.native import (
    NativeInputError,
    create_fds_derivative,
    create_fds_restartable_derivative,
    create_fds_resume_input,
    evaluate_fds_outputs,
    inspect_fds_input,
    sha256_file,
    validate_fds_cache,
    validate_openfoam_cache,
)


SOURCE = """&HEAD CHID='base_case', TITLE='test'/
&TIME T_END=1800.0 /
&DUMP DT_DEVC=10., DT_HRR=10. /
&DEVC ID='T', XYZ=0,0,0, QUANTITY='TEMPERATURE'/
&TAIL /
"""


class NativeTests(unittest.TestCase):
    def test_derivative_preserves_source_and_sets_output_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.fds"
            target = root / "run" / "smoke.fds"
            source.write_text(SOURCE, encoding="utf-8")
            before = source.read_bytes()
            result = create_fds_derivative(
                source,
                target,
                t_end_s=0.5,
                chid="smoke",
                trusted_root=root,
            )
            self.assertEqual(before, source.read_bytes())
            self.assertTrue(result["source_preserved_unchanged"])
            inspected = inspect_fds_input(target)
            self.assertEqual(inspected.chid, "smoke")
            self.assertEqual(inspected.t_end_s, 0.5)
            text = target.read_text(encoding="utf-8")
            self.assertIn("DT_DEVC=0.1", text)
            self.assertIn("DT_HRR=0.1", text)

    def test_input_outside_trusted_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            source = Path(first) / "case.fds"
            source.write_text(SOURCE, encoding="utf-8")
            with self.assertRaises(NativeInputError):
                inspect_fds_input(source, trusted_root=second)

    def test_restart_derivative_and_resume_require_matching_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.fds"
            checkpoint_input = root / "checkpoint.fds"
            resume_input = root / "resume.fds"
            checkpoint = root / "base_case.restart"
            source.write_text(SOURCE, encoding="utf-8")
            result = create_fds_restartable_derivative(
                source, checkpoint_input, restart_interval_s=60, trusted_root=root
            )
            self.assertTrue(result["identity_changed"])
            self.assertIn("DT_RESTART=60", checkpoint_input.read_text(encoding="utf-8"))
            checkpoint.write_bytes(b"native checkpoint")
            resumed = create_fds_resume_input(
                checkpoint_input,
                resume_input,
                restart_file=checkpoint,
                trusted_root=root,
            )
            self.assertEqual(len(resumed["checkpoint"]["sha256"]), 64)
            text = resume_input.read_text(encoding="utf-8")
            self.assertIn("RESTART=.TRUE.", text)
            self.assertIn("APPEND=.TRUE.", text)

    def test_resume_rejects_checkpoint_for_another_chid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.fds"
            checkpoint_input = root / "checkpoint.fds"
            source.write_text(SOURCE, encoding="utf-8")
            create_fds_restartable_derivative(source, checkpoint_input, restart_interval_s=60)
            wrong = root / "wrong.restart"
            wrong.write_bytes(b"checkpoint")
            with self.assertRaises(NativeInputError):
                create_fds_resume_input(checkpoint_input, root / "resume.fds", restart_file=wrong)

    def test_fake_success_marker_cannot_replace_time_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "case.out").write_text("STOP: FDS completed successfully\n", encoding="utf-8")
            result = evaluate_fds_outputs(root, "case", 10.0)
            self.assertTrue(result["success_marker"])
            self.assertFalse(result["time_covered"])
            self.assertFalse(result["required_artifacts_present"])

    def test_native_completion_requires_configured_time_in_csv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "case.out").write_text("STOP: FDS completed successfully\n", encoding="utf-8")
            (root / "case_hrr.csv").write_text('Time,HRR\ns,kW\n0,0\n10,1\n', encoding="utf-8")
            (root / "case_devc.csv").write_text('Time,T\ns,C\n0,20\n10,30\n', encoding="utf-8")
            result = evaluate_fds_outputs(root, "case", 10.0)
            self.assertTrue(result["time_covered"])
            self.assertTrue(result["required_artifacts_present"])
            self.assertEqual(result["completion_fraction"], 1.0)

    def test_completed_cache_rejects_deleted_or_corrupted_native_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "case.fds"
            out_path = root / "case.out"
            hrr_path = root / "case_hrr.csv"
            devc_path = root / "case_devc.csv"
            input_path.write_text(SOURCE.replace("base_case", "case"), encoding="utf-8")
            out_path.write_text("STOP: FDS completed successfully\n", encoding="utf-8")
            hrr_path.write_text("Time,HRR\ns,kW\n0,0\n1800,1\n", encoding="utf-8")
            devc_path.write_text("Time,T\ns,C\n0,20\n1800,30\n", encoding="utf-8")
            completion = evaluate_fds_outputs(root, "case", 1800.0)
            outputs = {
                path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
                for path in (input_path, out_path, hrr_path, devc_path)
            }
            manifest = {
                "status": "completed",
                "input": {"chid": "case", "t_end_s": 1800.0, "sha256": sha256_file(input_path)},
                "completion": completion,
                "outputs": outputs,
            }
            self.assertTrue(validate_fds_cache(root, manifest)["valid"])
            hrr_path.unlink()
            deleted = validate_fds_cache(root, manifest)
            self.assertFalse(deleted["valid"])
            self.assertTrue(any("missing cached output" in item for item in deleted["reasons"]))
            hrr_path.write_text("Time,HRR\ns,kW\n0,0\n1800,9\n", encoding="utf-8")
            corrupted = validate_fds_cache(root, manifest)
            self.assertFalse(corrupted["valid"])
            self.assertTrue(any("mismatch" in item for item in corrupted["reasons"]))

    def test_openfoam_cache_without_output_hashes_is_invalid(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = validate_openfoam_cache(
                temporary,
                {"status": "completed", "metrics": {"final_time_s": 0.2}},
            )
            self.assertFalse(result["valid"])
            self.assertIn("manifest has no output hash inventory", result["reasons"])


if __name__ == "__main__":
    unittest.main()
