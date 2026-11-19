param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Report,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$expectedPython = Join-Path $Root 'runtime\pythonw.exe'
$expectedTitle = '6517A · 고저항 측정'
$diagnostics = Join-Path $Root 'diagnostics'
$baseline = @(Get-Process -Name python, pythonw -ErrorAction SilentlyContinue |
    ForEach-Object { $_.Id })
$previousPlatform = $env:QT_QPA_PLATFORM
$started = [DateTime]::UtcNow
$main = $null
$passed = $false

function Get-BundleGuiProcesses {
    foreach ($process in @(Get-Process -Name pythonw -ErrorAction SilentlyContinue)) {
        if ($baseline -contains $process.Id) { continue }
        try {
            $image = [IO.Path]::GetFullPath($process.Path)
            if ($image.Equals($expectedPython, [StringComparison]::OrdinalIgnoreCase)) {
                $process
            }
        } catch {
            # A process can exit while Get-Process refreshes its properties.
        }
    }
}

try {
    if (!(Test-Path -LiteralPath $expectedPython -PathType Leaf)) {
        throw 'The extracted bundle does not contain runtime/pythonw.exe'
    }
    if (!(Test-Path -LiteralPath (Join-Path $Root 'Start-GUI.cmd') -PathType Leaf)) {
        throw 'The extracted bundle does not contain Start-GUI.cmd'
    }
    New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
    $oldReports = @(Get-ChildItem -LiteralPath $diagnostics -Filter 'startup-check-*.json' |
        ForEach-Object { $_.FullName })
    # The actual launcher sets the Windows Qt backend too. Scope this setting to this probe.
    $env:QT_QPA_PLATFORM = 'windows'
    Push-Location -LiteralPath $Root
    try {
        & $env:ComSpec /d /c Start-GUI.cmd
        if ($LASTEXITCODE -ne 0) { throw 'Start-GUI.cmd did not return successfully' }
    } finally {
        Pop-Location
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $startup = $null
    $startupPath = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        $fresh = @(Get-ChildItem -LiteralPath $diagnostics -Filter 'startup-check-*.json' |
            Where-Object { $oldReports -notcontains $_.FullName } |
            Sort-Object LastWriteTimeUtc -Descending)
        if ($fresh.Count -gt 0) {
            # A writer can still be flushing a newly created report; retry incomplete JSON.
            try {
                $candidate = Get-Content -LiteralPath $fresh[0].FullName -Raw -Encoding UTF8 |
                    ConvertFrom-Json
                if ($candidate.status -eq 'failed') {
                    throw "Actual GUI startup failed: $($candidate.details)"
                }
                if ($candidate.status -eq 'passed') {
                    $startup = $candidate
                    $startupPath = $fresh[0].Name
                }
            } catch [System.ArgumentException] {
                # ConvertFrom-Json can observe a partially written JSON report.
            }
        }
        foreach ($process in @(Get-BundleGuiProcesses)) {
            $process.Refresh()
            if ($process.MainWindowHandle -ne [IntPtr]::Zero -and
                $process.MainWindowTitle -eq $expectedTitle) {
                $main = $process
                break
            }
        }
        if ($null -ne $main -and $null -ne $startup) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($null -eq $main -or $null -eq $startup) {
        throw 'The actual CMD launcher did not show its main measurement window after startup'
    }
    if ($startup.checks.bundle.status -ne 'passed' -or
        $startup.checks.bundle.errors.Count -ne 0 -or
        $startup.checks.bundle.verified_files -le 0 -or
        $startup.checks.simulation.status -ne 'completed' -or
        $startup.checks.simulation.output_state -ne 'OFF' -or
        $startup.checks.simulation.reading_count -le 0 -or
        $startup.hardware_verified -ne $false -or
        $startup.automatic_output_enable -ne $false) {
        throw 'Actual CMD startup did not preserve Bundle/Simulation and output-enable checks'
    }
    # Obtain a process handle before closure so ExitCode remains available after exit.
    $null = $main.Handle
    $pidObserved = $main.Id
    $titleObserved = $main.MainWindowTitle
    $imageObserved = $main.Path
    if (!$main.CloseMainWindow() -or !$main.WaitForExit(10000)) {
        throw 'The actual GUI did not close its worker normally'
    }
    if ($main.ExitCode -ne 0) {
        throw "The actual GUI exited with code $($main.ExitCode)"
    }
    $result = [ordered]@{
        status = 'passed'
        scope = 'actual Start-GUI.cmd from the delivered ZIP; visible Windows main window'
        hardware_verified = $false
        automatic_output_enable = $false
        start_gui_cmd_verified = $true
        visible_main_window_verified = $true
        gui_normal_close_verified = $true
        gui_exit_code = $main.ExitCode
        process_id = $pidObserved
        image_path = $imageObserved
        window_title = $titleObserved
        startup_report = $startupPath
        root = $Root
        duration_s = ([DateTime]::UtcNow - $started).TotalSeconds
    }
    $encoded = $result | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($Report), $encoded, [Text.UTF8Encoding]::new($false))
    $passed = $true
    $encoded
} finally {
    $env:QT_QPA_PLATFORM = $previousPlatform
    if (!$passed) {
        # Close/stop only new processes running this fresh temporary bundle's interpreter.
        foreach ($process in @(Get-BundleGuiProcesses)) {
            try {
                $null = $process.CloseMainWindow()
                if (!$process.WaitForExit(10000)) { $process.Kill() }
            } catch {
                # Retain the original validation error.
            }
        }
    }
}
