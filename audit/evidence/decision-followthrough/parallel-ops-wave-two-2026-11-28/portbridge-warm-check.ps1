$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$launcher = Join-Path $root 'scripts/play.ps1'
$runner = Join-Path $PSScriptRoot 'portbridge-warm-runner.ps1'
$trace = Join-Path $PSScriptRoot 'portbridge-warm-calls.log'
$syntheticInput = Join-Path $root 'README.md'
$beforeDir = (Get-Location).Path
$env:VICTORY_TEST_WARM_PARENT = 'parent sentinel'

function Invoke-Scenario([int] $WarmExit) {
    Clear-Content -LiteralPath $trace
    $settings = @{
        VICTORY_TEST_WARM_PARENT = 'child sentinel'
        VICTORY_TEST_WARM_TRACE = $trace
        VICTORY_TEST_WARM_EXIT = "$WarmExit"
    }
    $caught = $null
    try {
        & $launcher -Exe $syntheticInput -Runner $runner -Warm -WarmJobs 3 -Console series-s -More $settings
    } catch {
        $caught = $_.Exception.Message
    }
    if ($env:VICTORY_TEST_WARM_PARENT -ne 'parent sentinel' -or (Get-Location).Path -ne $beforeDir) {
        throw 'Working directory or inherited setting was lost.'
    }
    if ($WarmExit -eq 0 -and $caught) { throw $caught }
    if ($WarmExit -ne 0 -and $caught -notmatch 'Pipeline warm-up exited with code 29') {
        throw 'A failed warm-up did not produce its explicit error.'
    }
    return @(Get-Content -LiteralPath $trace)
}

New-Item -ItemType File -Path $trace -Force | Out-Null
try {
    $succeeded = @(Invoke-Scenario 0)
    if ($succeeded.Count -ne 2 -or $succeeded[0] -ne 'warm|--used|--jobs|3' -or
        $succeeded[1] -notmatch '^run\|.*README\.md\|--console\|series-s\|--execute$') {
        throw 'A successful warm-up did not call warm once and run once.'
    }
    $failed = @(Invoke-Scenario 29)
    if ($failed.Count -ne 1 -or $failed[0] -ne 'warm|--used|--jobs|3') {
        throw 'A failed warm-up reached the run step or did not forward settings.'
    }
    'PASS: normal warm-up reaches the synthetic run; warm-up exit 29 blocks it; parent location and settings survive both.'
} finally {
    Remove-Item Env:VICTORY_TEST_WARM_PARENT -ErrorAction SilentlyContinue
    $global:LASTEXITCODE = 0
}
