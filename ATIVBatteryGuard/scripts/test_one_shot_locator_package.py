"""Freeze the approved one-shot boundary without executing Windows or OEM code."""
from pathlib import Path
import shutil
import tempfile
import unittest

from package_wmi_one_shot_query import (
    EXPERIMENT_REVISION, FROZEN_FILES, PROJECT_NAME, inspect_build, inspect_sources,
)


class OneShotLocatorPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ativ-one-shot-locator-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source_root = Path(__file__).resolve().parents[1]
        self.native = "src/" + PROJECT_NAME + "/WindowsOneShotBackend.cs"
        self.host = "src/" + PROJECT_NAME + "/Program.cs"
        names = set(FROZEN_FILES) | {
            self.native, self.host, "src/" + PROJECT_NAME + "/app.manifest",
            "WMI_ONE_SHOT_QUERY_APPROVAL.md",
            "src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj",
        }
        self.originals = {}
        for name in names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / name, target)
            self.originals[name] = target.read_text(encoding="utf-8")

    def reject_change(self, name, old, new):
        source = self.originals[name]
        self.assertIn(old, source, "fixture no longer contains the mutation target")
        target = self.root / name
        target.write_text(source.replace(old, new), encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                inspect_sources(self.root)
        finally:
            target.write_text(source, encoding="utf-8")

    def test_reviewed_locator_fix_preserves_the_original_one_shot_boundary(self):
        inspect_sources(self.root)

    def test_missing_or_expanded_locator_option_cannot_package(self):
        for old, new in [
            ("ensureLocatable: true", "ensureLocatable: false"),
            (", EnsureLocatable = ensureLocatable", ""),
            ("bool ensureLocatable = false", "bool ensureLocatable = true"),
            ("new ObjectQuery(query), CreateEnumerationOptions()",
             "new ObjectQuery(query), CreateEnumerationOptions(ensureLocatable: true)"),
        ]:
            with self.subTest(change=old):
                self.reject_change(self.native, old, new)

    def test_request_marker_claim_order_and_callback_semantics_cannot_change(self):
        changes = [
            ("src/ATIVBatteryGuard.Core/Services/WsabiWmiOneShotPolicy.cs",
             "CandidateCommand = 0x65", "CandidateCommand = 0x66"),
            ("src/ATIVBatteryGuard.Core/Services/WsabiWmiOneShotPolicy.cs",
             "MaximumInvocations = 1", "MaximumInvocations = 2"),
            ("src/ATIVBatteryGuard.Core/Services/WsabiWmiOneShotExperiment.cs",
             "claim = reservation.TryClaim();", "claim = WsabiWmiOneShotReservationStatus.Claimed;"),
            ("src/ATIVBatteryGuard.Core/Storage/WsabiWmiOneShotFileReservation.cs",
             "WmiQuery65-v1.attempt", "WmiQuery65-v2.attempt"),
            ("src/ATIVBatteryGuard.WmiOneShotQuery/OneShotResultCapture.cs",
             "if (completionStatus != 0)", "if (completionStatus < 0)"),
        ]
        for name, old, new in changes:
            with self.subTest(file=name, change=old):
                self.reject_change(name, old, new)

    def test_dispatch_preflight_guards_host_limits_and_claim_directory_cannot_change(self):
        changes = [
            (self.native, "selectedTarget.InvokeMethod(observer,", "selectedTarget.InvokeMethod(null,"),
            (self.native, "input.Properties.Count != 1", "input.Properties.Count > 1"),
            (self.native, "MaximumDetachedBytes = 4096", "MaximumDetachedBytes = 8192"),
            (self.host, "WorkerTimeoutMilliseconds = 10000", "WorkerTimeoutMilliseconds = 20000"),
            (self.host, '"Experiments"', '"Experiments-v2"'),
        ]
        for name, old, new in changes:
            with self.subTest(file=name, change=old):
                self.reject_change(name, old, new)

    def test_previous_experiment_or_preflight_binary_cannot_satisfy_the_revision_markers(self):
        setter = b"fixture\0set_EnsureLocatable\0"
        revision = EXPERIMENT_REVISION.encode("utf-16-le")
        inspect_build(setter + revision)
        for stale in (b"previous experiment", setter, revision, setter + "Locator-v2".encode("utf-16-le")):
            with self.subTest(binary=stale):
                with self.assertRaises(ValueError):
                    inspect_build(stale)


if __name__ == "__main__":
    unittest.main()
