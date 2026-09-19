import json
import struct
import tempfile
import unittest
from pathlib import Path

from firelab.fields import FieldFormatError, export_fds_fields, parse_smv, read_fds_slice


def _record(payload: bytes) -> bytes:
    marker = struct.pack("<I", len(payload))
    return marker + payload + marker


def _fixture(root: Path, *, wrong_label: bool = False) -> tuple[Path, Path]:
    sf = root / "sample.sf"
    labels = ("TEMPERATURE", "temp", "C")
    content = b"".join(_record(label.ljust(30).encode("ascii")) for label in labels)
    content += _record(struct.pack("<6i", 0, 2, 0, 0, 0, 1))
    content += _record(struct.pack("<f", 0.0))
    content += _record(struct.pack("<6f", 1, 2, 3, 4, 5, 6))
    content += _record(struct.pack("<f", 1.0))
    content += _record(struct.pack("<6f", 2, 3, 4, 5, 6, 7))
    sf.write_bytes(content)
    smv = root / "sample.smv"
    quantity = "WRONG" if wrong_label else "TEMPERATURE"
    smv.write_text(
        "\n".join(
            [
                "GRID mesh1",
                " 2 1 1 0 0 0 0 0 0",
                "PDIM",
                " 0 2 0 1 0 1 0 0 0",
                "TRNX",
                " 0",
                " 0 0.0",
                " 1 0.5",
                " 2 2.0",
                "TRNY",
                " 0",
                " 0 0.0",
                " 1 1.0",
                "TRNZ",
                " 0",
                " 0 0.0",
                " 1 1.0",
                "SLCF 1 # STRUCTURED & 0 2 0 0 0 1 ! 1 0 2",
                " sample.sf",
                f" {quantity}",
                " temp",
                " C",
            ]
        ),
        encoding="utf-8",
    )
    return sf, smv


class FieldTests(unittest.TestCase):
    def test_exact_fortran_slice_and_coordinates(self):
        with tempfile.TemporaryDirectory() as temporary:
            sf, smv = _fixture(Path(temporary))
            field = read_fds_slice(sf, smv)
            self.assertEqual(field["quantity"], "TEMPERATURE")
            self.assertEqual(field["frame_count"], 2)
            self.assertEqual(field["frames"][1]["values"], [2, 3, 4, 5, 6, 7])
            self.assertEqual(field["geometry"]["axes_m"]["x"], [0.0, 0.5, 2.0])
            self.assertEqual(field["geometry"]["shape_kji"], [2, 1, 3])
            self.assertEqual(field["geometry"]["topology"], "plane")

    def test_smv_binary_label_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            sf, smv = _fixture(Path(temporary), wrong_label=True)
            with self.assertRaisesRegex(FieldFormatError, "labels differ"):
                read_fds_slice(sf, smv)

    def test_truncated_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            sf, smv = _fixture(Path(temporary))
            sf.write_bytes(sf.read_bytes()[:-2])
            with self.assertRaisesRegex(FieldFormatError, "truncated"):
                read_fds_slice(sf, smv)

    def test_export_is_json_serializable_and_retains_plane_topology(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture(root)
            output = root / "fields.json"
            result = export_fds_fields(root, output)
            self.assertEqual(result["field_count"], 1)
            self.assertEqual(result["fields"][0]["geometry"]["topology"], "plane")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["field_count"], 1)

    def test_repository_native_smoke_slice_reads_as_real_plane(self):
        run = Path(__file__).parents[1] / "runs" / "fds_steckler_smoke_1s_actual"
        if not run.is_dir():
            self.skipTest("native smoke artifact is not present")
        metadata = parse_smv(run / "Steckler_010_smoke.smv")
        self.assertEqual(metadata["meshes"][0]["cell_counts"], [72, 56, 44])
        result = export_fds_fields(run)
        self.assertEqual(result["field_count"], 4)
        self.assertTrue(all(item["geometry"]["topology"] == "plane" for item in result["fields"]))
        self.assertTrue(all(item["frame_count"] >= 1 for item in result["fields"]))


if __name__ == "__main__":
    unittest.main()
