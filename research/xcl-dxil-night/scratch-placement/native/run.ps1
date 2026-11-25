param(
    [Parameter(Mandatory)] [ValidateSet('Verify', 'Measure')] [string] $Stage,
    [Parameter(Mandatory)] [string] $LogDirectory
)

$ErrorActionPreference = 'Stop'
$probe = Join-Path $PSScriptRoot 'scratch_probe.exe'
$directory = (Resolve-Path -LiteralPath $LogDirectory).ProviderPath
$verification = Join-Path $directory 'verify.log'

if ($Stage -eq 'Measure') {
    $verified = Get-Content -LiteralPath $verification
    if ($verified[0] -notmatch '^guard=returned reaped=1 child_exit=0 win_error=0 ' -or
        $verified[1] -notmatch '\bdiagnostics=0\b.*\bhresult=00000000\b.*\bcomplete=2 started=2\b') {
        throw 'Both arms must have a clean verification log before measuring.'
    }
    $modes = @('measure-ab', 'measure-ba')
} else {
    $modes = @('verify')
}

foreach ($mode in $modes) {
    $log = Join-Path $directory "$mode.log"
    if (Test-Path -LiteralPath $log) { throw "Existing log will be retained: $log" }
    & $probe $mode | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "Probe stopped in $mode. See $log." }
}
