from pathlib import Path
import shutil
import tempfile
import unittest
from package_acpi_routing_check import PROJECT, inspect_reader_sources


class AcpiRoutingPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ativ-acpi-package-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = Path(__file__).resolve().parents[1]
        for name in ['src/'+PROJECT+'/Program.cs', 'src/'+PROJECT+'/WindowsAcpiRoutingProbe.cs',
                'src/'+PROJECT+'/'+PROJECT+'.csproj', 'src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj',
                'src/ATIVBatteryGuard.Core/Services/AcpiWmiRoutingInspector.cs']:
            p=self.root/name; p.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source/name,p)

    def test_current_reader_is_read_only_and_separate(self):
        inspect_reader_sources(self.root)

    def test_other_providers_and_native_or_storage_actions_cannot_package(self):
        p=self.root/'src'/PROJECT/'WindowsAcpiRoutingProbe.cs'
        original=p.read_text()
        for old,new in [('0x41435049','0x52534d42'), ('GetSystemFirmwareTable','SetFirmwareEnvironmentVariable'),
                        ('var text = new StringBuilder();','var text = new StringBuilder(); File.WriteAllText("raw", "data");')]:
            with self.subTest(change=old):
                p.write_text(original.replace(old,new))
                with self.assertRaises(ValueError): inspect_reader_sources(self.root)
        p.write_text(original)

    def test_worker_limit_or_wmi_dependency_changes_cannot_package(self):
        p=self.root/'src'/PROJECT/'Program.cs'; original=p.read_text()
        p.write_text(original.replace('WorkerTimeoutMilliseconds = 10000','WorkerTimeoutMilliseconds = 20000'))
        with self.assertRaises(ValueError): inspect_reader_sources(self.root)
        p.write_text(original)
        project=self.root/'src'/PROJECT/(PROJECT+'.csproj')
        project.write_text(project.read_text().replace('</Project>','<ItemGroup><Reference Include="System.Management" /></ItemGroup></Project>'))
        with self.assertRaises(ValueError): inspect_reader_sources(self.root)


if __name__ == '__main__': unittest.main()
