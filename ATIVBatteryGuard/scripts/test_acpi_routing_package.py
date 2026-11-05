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
                'src/ATIVBatteryGuard.Core/Services/AcpiWmiRoutingInspector.cs',
                'src/ATIVBatteryGuard.Core/Models/AcpiWmiRoutingReport.cs',
                'src/ATIVBatteryGuard.Core/Models/AcpiMethodFlowReport.cs',
                'src/ATIVBatteryGuard.Core/Models/AcpiObjectReferenceReport.cs',
                'src/ATIVBatteryGuard.Core/Models/AcpiFieldChannelReport.cs',
                'src/ATIVBatteryGuard.Core/Models/AcpiStoreRoleReport.cs']:
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

    def test_direct_dsdt_gate_and_revision_regressions_cannot_package(self):
        p=self.root/'src'/PROJECT/'WindowsAcpiRoutingProbe.cs'; original=p.read_text()
        for old,new in [('if (id == DsdtId)', 'if (id == DsdtId && occurrences != 0)'),
                        ('Acpi-routing-v7', 'Acpi-routing-v6')]:
            with self.subTest(change=old):
                self.assertIn(old, original)
                p.write_text(original.replace(old,new))
                with self.assertRaises(ValueError): inspect_reader_sources(self.root)
        p.write_text(original)

    def test_pure_flow_models_cannot_hide_native_network_or_storage_actions(self):
        for name in ['AcpiWmiRoutingReport.cs', 'AcpiMethodFlowReport.cs', 'AcpiObjectReferenceReport.cs', 'AcpiFieldChannelReport.cs', 'AcpiStoreRoleReport.cs']:
            p=self.root/'src/ATIVBatteryGuard.Core/Models'/name; original=p.read_text()
            for extra in ['[DllImport("kernel32.dll")] private static extern int NewNativeCall();',
                          'private void Save() { File.WriteAllBytes("raw", new byte[1]); }',
                          'private void Send() { var client = new HttpClient(); }']:
                with self.subTest(model=name, action=extra):
                    p.write_text(original+'\n'+extra)
                    with self.assertRaises(ValueError): inspect_reader_sources(self.root)
            p.write_text(original)

    def test_store_role_statement_bound_cannot_be_increased_or_removed(self):
        p=self.root/'src/ATIVBatteryGuard.Core/Services/AcpiWmiRoutingInspector.cs'; original=p.read_text()
        import re
        for replacement in ['MaximumStoreRoleStatements = 128;', 'RemovedStoreRoleBound = 64;']:
            changed=re.sub(r'\bMaximumStoreRoleStatements\s*=\s*64\s*;', replacement, original)
            self.assertNotEqual(original, changed)
            p.write_text(changed)
            with self.assertRaises(ValueError): inspect_reader_sources(self.root)
        p.write_text(original)

    def test_mutex_declaration_kind_is_data_while_runtime_mutex_apis_are_blocked(self):
        p=self.root/'src/ATIVBatteryGuard.Core/Models/AcpiObjectReferenceReport.cs'; original=p.read_text()
        self.assertIn('Mutex', original)
        inspect_reader_sources(self.root)
        for extra in ['private void Run() { var mutex = new Mutex(); }',
                      'private void Run() { Mutex.OpenExisting("existing"); }',
                      'using RuntimeMutex = System.Threading.Mutex;']:
            with self.subTest(action=extra):
                p.write_text(original+'\n'+extra)
                with self.assertRaises(ValueError): inspect_reader_sources(self.root)
        p.write_text(original)

    def test_parsing_wait_syntax_must_not_introduce_real_wait_or_sync_calls(self):
        for relative in ['Services/AcpiWmiRoutingInspector.cs', 'Models/AcpiMethodFlowReport.cs']:
            p=self.root/'src/ATIVBatteryGuard.Core'/relative; original=p.read_text()
            for extra in ['private void Wait() { System.Threading.Thread.Sleep(1); }',
                          'private void Wait() { var wait = new Mutex(); }']:
                with self.subTest(source=relative, action=extra):
                    p.write_text(original+'\n'+extra)
                    with self.assertRaises(ValueError): inspect_reader_sources(self.root)
            p.write_text(original)


if __name__ == '__main__': unittest.main()
