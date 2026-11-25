"""Package a separate WPF harness with byte-identical RC2 product files."""
import argparse
import json
import zipfile
import xml.etree.ElementTree as ET
import dnfile
from pathlib import Path
from package_manual_control_beta import PROGRAM_NAMES, execution_level, sha, source_closure
from package_release_020 import gui_version

VERSION = '0.3.0-rc.2'


def validate_host(tool_bytes):
    pe = dnfile.dnPE(data=tool_bytes)
    hosts = [row for row in pe.net.mdtables.TypeDef if str(row.TypeName) == 'ExtendedApplication']
    if len(hosts) != 1:
        raise ValueError('One isolated WPF host is required.')
    parent = hosts[0].Extends.row
    if str(parent.TypeNamespace) != 'System.Windows' or str(parent.TypeName) != 'Application':
        raise ValueError('The harness must not derive from the product App across assemblies.')
    keys = [str(entry.name) for resource in pe.net.resources if str(resource.name).endswith('.g.resources')
            for entry in resource.data.entries]
    if 'productresources.baml' not in keys:
        raise ValueError('The host-owned resource dictionary was not compiled.')
    return dict(hostBase='System.Windows.Application', ownResourceDictionaryBamlPresent=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-zip', required=True, type=Path)
    parser.add_argument('--test-report', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text())
    if not (suite['passed'] >= 1263 and suite['registered'] == suite['passed']
            and suite['failed'] == 0 and suite['skipped'] == 0):
        raise ValueError('The existing and extended validation regressions must pass.')
    released = json.loads((root/'reports/release-030-rc2-validation.json').read_text())
    if sha(args.candidate_zip.read_bytes()) != released['package']['sha256']:
        raise ValueError('Use the previously released, unchanged RC2 candidate ZIP.')
    with zipfile.ZipFile(args.candidate_zip) as z:
        expected = set(PROGRAM_NAMES) | {'BUILD-INFO.json', '먼저 읽어주세요.txt', 'SHA256SUMS.txt'}
        if len(z.namelist()) != 9 or set(z.namelist()) != expected or z.testzip() is not None:
            raise ValueError('Candidate allowlist or CRC differs.')
        files = {name: z.read(name) for name in z.namelist()}
    info = json.loads(files['BUILD-INFO.json'])
    if info['releaseVersion'] != VERSION or info['final030ReleaseApproved']:
        raise ValueError('Not the frozen RC2 validation candidate.')
    for line in files['SHA256SUMS.txt'].decode().splitlines():
        digest, name = line.split('  ', 1)
        if name not in files or sha(files[name]) != digest:
            raise ValueError('Candidate internal hash differs.')
    for entry in info['programFiles']:
        if entry['file'] not in PROGRAM_NAMES or sha(files[entry['file']]) != entry['sha256'] or len(files[entry['file']]) != entry['bytes']:
            raise ValueError('Candidate program metadata differs.')
    for entry in info['sourceFiles']:
        if sha((root/entry['file']).read_bytes()) != entry['sha256']:
            raise ValueError('Product source changed; this harness is for frozen RC2 only.')
    ns = '{http://schemas.microsoft.com/winfx/2006/xaml/presentation}'
    app_resources = ET.parse(root/'src/ATIVBatteryGuard.App/App.xaml').getroot().find(ns+'Application.Resources')
    host_resources = ET.parse(root/'validation/ATIVBatteryGuard.ExtendedCheck/ProductResources.xaml').getroot()
    if host_resources.tag != ns+'ResourceDictionary' or len(app_resources) != len(host_resources):
        raise ValueError('Host dictionary root or product resource count differs.')
    for original, isolated in zip(app_resources, host_resources):
        if ET.tostring(original) != ET.tostring(isolated):
            raise ValueError('Host dictionary changed product UI resources.')
    tool_project = root/'validation/ATIVBatteryGuard.ExtendedCheck/ATIVBatteryGuard.ExtendedCheck.csproj'
    build = tool_project.parent/'bin/Release/net48'
    for name in PROGRAM_NAMES:
        if name.endswith('.config') or name in ('ATIVBatteryGuard.WmiInterop.dll', 'ATIVBatteryGuard.ManualProtectionHelper.exe'):
            continue
        if (build/name).read_bytes() != files[name]:
            raise ValueError('Harness references do not match frozen product assemblies.')
    tool_name = 'ATIVBatteryGuard.ExtendedCheck.exe'
    tool_bytes = (build/tool_name).read_bytes()
    execution_level(tool_bytes); gui_version(tool_bytes, VERSION)
    host_audit = validate_host(tool_bytes)
    gui_version(files['ATIVBatteryGuard.exe'], VERSION)
    files[tool_name] = tool_bytes
    files[tool_name+'.config'] = (build/(tool_name+'.config')).read_bytes()
    manifest = dict(SchemaVersion=1, ReleaseVersion=VERSION,
                    SourceFingerprintSha256=info['productSourceFingerprintSha256'],
                    ProgramFiles=[dict(Name=n, Bytes=len(files[n]), Sha256=sha(files[n])) for n in PROGRAM_NAMES])
    files['EXTENDED-MANIFEST.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    sources = sorted(source_closure(root, tool_project))
    fingerprint = sha(b''.join(n.encode()+b'\0'+d+b'\0' for n, d in sources))
    files['EXTENDED-INFO.json'] = (json.dumps(dict(toolRevision='extended-v2', releaseVersion=VERSION,
        productZipSha256=sha(args.candidate_zip.read_bytes()), productSourceFingerprintSha256=info['productSourceFingerprintSha256'],
        toolSourceFingerprintSha256=fingerprint, toolSourceFileCount=len(sources),
        toolSha256=sha(tool_bytes),
        hostResourceDictionarySha256=sha((tool_project.parent/'ProductResources.xaml').read_bytes()),
        hostResourcesEquivalentToFrozenProduct=True, startupDiagnosticsEnabled=True,
        hostBinaryAudit=host_audit,
        fixtureSourceHashes={name: sha((root/'validation/samples'/name).read_bytes()) for name in ('sample-a.ativrecord', 'sample-b.ativrecord')},
        windowsToolExecutedInCloud=False, actualImeCompositionTested=False,
        signed=False, finalReleaseApproved=False, originalProgramGuideFile='원본프로그램안내.txt'), indent=2)+'\n').encode()
    for name, mode in (('빠른추가검사.cmd', '--quick'), ('20분반복검사.cmd', '--soak')):
        files[name] = ('@echo off\r\nsetlocal\r\n"%~dp0ATIVBatteryGuard.ExtendedCheck.exe" '+mode+'\r\nset "ativ_extended_exit=%ERRORLEVEL%"\r\necho.\r\npause\r\nexit /b %ativ_extended_exit%\r\n').encode('ascii')
    files['원본프로그램안내.txt'] = files.pop('먼저 읽어주세요.txt')
    files['먼저 읽어주세요.txt'] = (root/'EXTENDED_030_USER_STEPS.txt').read_text().replace('\n','\r\n').encode('utf-8-sig')
    for name in ('sample-a.ativrecord', 'sample-b.ativrecord'):
        files['예제/'+name] = (root/'validation/samples'/name).read_bytes()
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items()) if name != 'SHA256SUMS.txt').encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/f'ATIVBatteryGuard-{VERSION}-EXTENDED-CHECKS-v2.zip'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()): z.writestr(name,data)
    with zipfile.ZipFile(target) as z:
        assert len(z.namelist()) == len(files) == 18 and z.testzip() is None
        for name,data in files.items(): assert z.read(name) == data
    print(json.dumps(dict(file=target.name, bytes=target.stat().st_size, sha256=sha(target.read_bytes()),
        entries=len(files), releaseVersion=VERSION, toolSourceFileCount=len(sources),
        toolSourceFingerprintSha256=fingerprint, productSourceFingerprintSha256=info['productSourceFingerprintSha256'])))


if __name__ == '__main__':
    main()
