"""Check the offline review release boundary without running Windows code."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from package_experiment_review import REVIEW_TYPES, inspect_review_build, inspect_review_sources


class ExperimentReviewPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ativ-result-review-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source_root = Path(__file__).resolve().parents[1]
        names = [
            "src/ATIVBatteryGuard.App/app.manifest",
            "src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj",
            "src/ATIVBatteryGuard.App/ViewModels/MainViewModel.cs",
            "src/ATIVBatteryGuard.Core/Models/WsabiWmiExperimentReview.cs",
            "src/ATIVBatteryGuard.Core/Services/WsabiWmiExperimentReviewParser.cs",
            "src/ATIVBatteryGuard.Core/Models/WsabiWmiReplyResult.cs",
            "src/ATIVBatteryGuard.Core/Services/WsabiWmiReplyDecoder.cs",
        ]
        for name in names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / name, target)

    def test_reviewed_offline_source_keeps_hardware_and_controls_separate(self):
        inspect_review_sources(self.root)

    def test_device_storage_and_control_links_cannot_be_added_to_review(self):
        path = self.root / "src/ATIVBatteryGuard.App/ViewModels/MainViewModel.cs"
        source = path.read_text(encoding="utf-8")
        anchor = "public void ReviewExperimentResult()\n\t\t{"
        self.assertIn(anchor, source)
        for injected in ("physical.GetCurrentMode();", "log.Write(experimentReviewInput);", "File.ReadAllText(\"marker\");"):
            with self.subTest(operation=injected):
                path.write_text(source.replace(anchor, anchor + "\n\t\t\t" + injected), encoding="utf-8")
                with self.assertRaises(ValueError):
                    inspect_review_sources(self.root)

    def test_previous_application_or_core_cannot_satisfy_the_review_build_markers(self):
        executable = b"fixture\0ReviewExperimentResult\0"
        core = b"\0".join(name.encode("ascii") for name in REVIEW_TYPES) + b"\0"
        inspect_review_build(executable, core)
        for stale_executable, stale_core in ((b"previous app", core), (executable, b"previous core")):
            with self.subTest(executable=stale_executable, core=stale_core):
                with self.assertRaises(ValueError):
                    inspect_review_build(stale_executable, stale_core)

    def test_v1_core_without_firmware_prefix_classifier_is_rejected(self):
        core = b"WsabiWmiExperimentReview\0WsabiWmiExperimentReviewParser\0"
        with self.assertRaises(ValueError):
            inspect_review_build(b"ReviewExperimentResult\0", core)

    def test_completed_one_shot_cli_creates_no_further_oem_distribution(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        source_scripts = Path(__file__).resolve().parent
        for name in ("package_wmi_one_shot_query.py", "package_wmi_preflight_check.py"):
            shutil.copyfile(source_scripts / name, scripts / name)
        (self.root / "WMI_ONE_SHOT_QUERY_RESULT.md").write_text("completed fixed test record", encoding="utf-8")
        output = self.root / "output"
        result = subprocess.run([
            sys.executable, str(scripts / "package_wmi_one_shot_query.py"),
            "--test-report", "not-needed.json", "--source-zip", "not-needed.zip", "--output", str(output),
        ], capture_output=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn(b"Further OEM executable distribution is closed", result.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
