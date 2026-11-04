"""Check the locator-only packaging scope without loading Windows or OEM code."""
from pathlib import Path
import shutil
import tempfile
import unittest

from package_wmi_preflight_check import (
    DIAGNOSTIC_REVISION, PROJECT_NAME, inspect_locator_build, inspect_sources,
)


class PreflightLocatorPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ativ-locator-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source_root = Path(__file__).resolve().parents[1]
        self.project = self.root / "src" / PROJECT_NAME
        self.project.mkdir(parents=True)
        for name in ("Program.cs", "ReadOnlyPreparationProbe.cs", "app.manifest"):
            shutil.copyfile(source_root / "src" / PROJECT_NAME / name, self.project / name)
        app = self.root / "src/ATIVBatteryGuard.App"
        app.mkdir()
        shutil.copyfile(source_root / "src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj",
                        app / "ATIVBatteryGuard.App.csproj")
        self.native = self.project / "ReadOnlyPreparationProbe.cs"
        self.original = self.native.read_text(encoding="utf-8")

    def reject_native_change(self, old, new):
        self.assertIn(old, self.original, "fixture no longer contains the mutation target")
        self.native.write_text(self.original.replace(old, new), encoding="utf-8")
        with self.assertRaises(ValueError):
            inspect_sources(self.root, self.project)

    def test_reviewed_source_accepts_only_the_method_target_locator_option(self):
        inspect_sources(self.root, self.project)

    def test_missing_or_disabled_locator_option_cannot_package(self):
        changes = [
            ("ensureLocatable: true", "ensureLocatable: false"),
            (", EnsureLocatable = ensureLocatable", ""),
            ("EnsureLocatable = ensureLocatable", "EnsureLocatable = false"),
        ]
        for old, new in changes:
            with self.subTest(change=old):
                self.reject_native_change(old, new)

    def test_locator_scope_expansion_and_query_expansion_cannot_package(self):
        changes = [
            ("bool ensureLocatable = false", "bool ensureLocatable = true"),
            ("new ObjectQuery(query), CreateEnumerationOptions()",
             "new ObjectQuery(query), CreateEnumerationOptions(ensureLocatable: true)"),
            ("SELECT Active FROM WmiAcpiMethod", "SELECT * FROM WmiAcpiMethod"),
            ("SELECT SMBIOSBIOSVersion FROM Win32_BIOS", "SELECT SerialNumber FROM Win32_BIOS"),
        ]
        for old, new in changes:
            with self.subTest(change=old):
                self.reject_native_change(old, new)

    def test_previous_exe_or_core_cannot_satisfy_the_locator_build_markers(self):
        executable = b"fixture\0set_EnsureLocatable\0"
        core = DIAGNOSTIC_REVISION.encode("utf-16-le")
        inspect_locator_build(executable, core)
        for stale_executable, stale_core in ((b"previous exe", core), (executable, b"previous core")):
            with self.subTest(executable=stale_executable, core=stale_core):
                with self.assertRaises(ValueError):
                    inspect_locator_build(stale_executable, stale_core)


if __name__ == "__main__":
    unittest.main()
