"""Run the reviewed original fixture checker, with an additional native-evidence gate."""
from pathlib import Path
import importlib.util
import sys
import json
from .intake import json_write

def audit_reference(root):
    root = Path(root).resolve()
    refs = root / "data" / "reference"
    module_path = refs / "adapter_contract.py"
    if not module_path.is_file():
        return {"status": "missing_sources", "comparable": False}
    spec = importlib.util.spec_from_file_location("firelab_original_adapter", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    config = json.loads((refs / "fixture_contract.json").read_text(encoding="utf-8-sig"))
    for artifact in config["artifacts"]:
        artifact["path"] = str(refs / Path(artifact["path"]).name)
    checks = config["native_artifact_checks"]
    checks["fds_input_path"] = str(refs / "Steckler_010.fds")
    checks["fds_run_manifest_path"] = str(refs / "run_manifest.json")
    checks["fds_output_path"] = str(refs / "not_supplied" / "Steckler_010.out")
    checks["openfoam_case_path"] = str(refs / "not_supplied" / "openfoam")
    config["output_dir"] = str(root / "reports" / "reference_audit")
    path = root / "configs" / "reference_audit.json"
    json_write(path, config)
    report = module.run(path)
    # The original pairing implementation does not feed all native failures back
    # into its stage gates. Preserve its output, but never promote it to validation.
    native = report.get("native_artifact_report", {})
    report["comparable"] = all(g["status"] == "ready" for g in report["gates"]) and all(
        x.get("status") == "ready" for x in native.values()
    )
    report["status"] = "ready" if report["comparable"] else "blocked"
    report["scope"] = "Original supplied fixture only; not new solver output."
    json_write(root / "reports" / "reference_audit" / "summary.json", report)
    return report
