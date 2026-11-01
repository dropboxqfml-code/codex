# Developer release verification. Run after legitimate publisher signing.
# Does not change Defender settings, exclusions, signatures, or quarantine.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$SourceFingerprint,
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
$build = (Resolve-Path -LiteralPath $BuildDirectory).Path
$reportFull = [IO.Path]::GetFullPath($ReportPath)
if (Test-Path -LiteralPath $reportFull) { throw 'Use a new evidence report path; old evidence is not overwritten.' }
if ((Get-Item -LiteralPath $build).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked build folder rejected.' }
$names = @('ATIVBatteryGuard.exe','ATIVBatteryGuard.Core.dll','ATIVBatteryGuard.exe.config')
$before = @{}
$signatures = @{}
foreach ($name in $names) {
    $file = Join-Path $build $name
    if ((Get-Item -LiteralPath $file).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked artifact rejected.' }
    $before[$name] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($name -ne 'ATIVBatteryGuard.exe.config') {
        $sig = Get-AuthenticodeSignature -LiteralPath $file
        if ($sig.Status -ne 'Valid' -or !$sig.SignerCertificate) { throw "Publisher signature not valid: $name" }
        $signatures[$name] = @{status='Valid'; thumbprint=$sig.SignerCertificate.Thumbprint}
    }
}
if ($signatures[$names[0]].thumbprint -ne $signatures[$names[1]].thumbprint) { throw 'Publisher certificates differ.' }
$status = Get-MpComputerStatus
if (!$status.AntivirusEnabled -or !$status.RealTimeProtectionEnabled -or !$status.AntivirusSignatureVersion -or $status.AntivirusSignatureAge -gt 7) {
    throw 'Defender must be enabled with current definitions and real-time protection.'
}
$candidates = @()
$platform = Join-Path $env:ProgramData 'Microsoft\Windows Defender\Platform'
if (Test-Path -LiteralPath $platform) {
    $candidates += Get-ChildItem -LiteralPath $platform -Directory | Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'MpCmdRun.exe' }
}
$candidates += Join-Path $env:ProgramFiles 'Windows Defender\MpCmdRun.exe'
$scanner = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (!$scanner) { throw 'Microsoft Defender scanner unavailable.' }
$scannerSig = Get-AuthenticodeSignature -LiteralPath $scanner
if ($scannerSig.Status -ne 'Valid' -or $scannerSig.SignerCertificate.Subject -notmatch 'Microsoft') { throw 'Scanner signature not verified.' }
& $scanner -Scan -ScanType 3 -File $build
if ($LASTEXITCODE -ne 0) { throw 'Defender scan failed or reported a threat.' }
# Exit code zero alone can also mean a threat was remediated. Check detection
# resources and artifact hashes as well; never release quarantined/changed files.
$detections = @(Get-MpThreatDetection | Where-Object {
    $match = $false
    foreach ($resource in $_.Resources) {
        if ($resource.IndexOf($build, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $match = $true }
    }
    $match
})
if ($detections.Count -ne 0) { throw 'Defender detection evidence exists for this build folder.' }
foreach ($name in $names) {
    if ((Get-FileHash -LiteralPath (Join-Path $build $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $before[$name]) { throw 'Scanned artifact changed or was quarantined.' }
}
$after = Get-MpComputerStatus
if (!$after.AntivirusEnabled -or !$after.RealTimeProtectionEnabled) { throw 'Protection state changed during verification.' }
$report = @{
    schemaVersion=1; sourceFingerprintSha256=$SourceFingerprint
    completedUtc=[DateTime]::UtcNow.ToString('o')
    defenderEnabled=$true; realTimeProtectionEnabled=$true
    scanCompleted=$true; scanPassed=$true; detections=0
    defenderSignatureVersion=$after.AntivirusSignatureVersion
    fileHashes=$before; signatures=$signatures
}
$json = $report | ConvertTo-Json -Depth 6
$stream = [IO.File]::Open($reportFull, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream.Write($bytes, 0, $bytes.Length)
} finally { $stream.Dispose() }
Write-Output 'Release evidence written. This is a scan observation, not a permanent safety guarantee.'
