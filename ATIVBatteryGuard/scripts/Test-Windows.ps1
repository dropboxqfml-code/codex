param([string]$Configuration = 'Release')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$reports = Join-Path $projectRoot 'reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null

& dotnet build (Join-Path $projectRoot 'ATIVBatteryGuard.sln') --configuration $Configuration
if ($LASTEXITCODE -ne 0) { throw 'Windows WPF build failed.' }
$testReport = Join-Path $reports ('portable-' + [guid]::NewGuid().ToString('N') + '.json')
& dotnet run --project (Join-Path $projectRoot 'tests/ATIVBatteryGuard.PortableTests.csproj') --configuration $Configuration -- --report $testReport
if ($LASTEXITCODE -ne 0) { throw 'Portable regression tests failed.' }
$tests = Get-Content -Raw -LiteralPath $testReport | ConvertFrom-Json
if ($tests.passed -le 0 -or $tests.failed -ne 0) { throw 'Invalid portable test results.' }

$exe = Join-Path $projectRoot ('src/ATIVBatteryGuard.App/bin/' + $Configuration + '/net48/ATIVBatteryGuard.exe')
$smokeReport = Join-Path $reports ('windows-smoke-' + [guid]::NewGuid().ToString('N') + '.json')
$process = Start-Process -FilePath $exe -ArgumentList @('--self-test', ('"' + $smokeReport + '"')) -PassThru
if (-not $process.WaitForExit(90000)) {
    $process.Kill()
    throw 'Windows GUI self-test exceeded 90 seconds.'
}
if ($process.ExitCode -ne 0) { throw 'Windows GUI self-test failed.' }
$smoke = Get-Content -Raw -LiteralPath $smokeReport | ConvertFrom-Json
if ($smoke.status -ne 'passed' -or -not $smoke.guiPassed -or $smoke.hardwareWritesPerformed -or $smoke.bindingErrors -ne 0) {
    throw 'Invalid Windows GUI self-test results.'
}
Write-Output ('PASS: portable=' + $tests.passed + ', Windows GUI=passed. Reports: ' + $reports)
