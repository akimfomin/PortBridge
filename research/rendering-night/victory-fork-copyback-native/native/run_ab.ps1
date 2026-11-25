param(
    [Parameter(Mandatory)] [string] $Worker,
    [Parameter(Mandatory)] [string] $Sha256,
    [Parameter(Mandatory)] [string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
if ((Get-FileHash -LiteralPath $Worker).Hash -ne $Sha256) { throw 'Unreviewed worker binary.' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new evidence directory.' }
$out = (New-Item -ItemType Directory -Path $OutputDirectory).FullName

foreach ($arm in 'a','b') {
    $memory = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
    $commit = [uint64]($memory.CommitLimit - $memory.CommittedBytes)
    $physical = [uint64]$memory.AvailableBytes
    @{polarity=$arm; commit_available=$commit; physical_available=$physical;
      admitted=($commit -ge 4GB -and $physical -ge 6GB)} |
        ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $out "preflight-$arm.json") -Encoding utf8
    if ($commit -lt 4GB -or $physical -lt 6GB) { throw "Stopped before $arm because the hardware gate declined." }
    & $Worker "--hardware-$arm" | Tee-Object -FilePath (Join-Path $out "result-$arm.csv")
    if ($LASTEXITCODE -ne 0) { throw "Guard or readback declined on $arm. Stopping the campaign." }
}

& python -I -B (Join-Path $PSScriptRoot 'analyze.py') (Join-Path $out 'result-a.csv') (Join-Path $out 'result-b.csv') |
    Tee-Object -FilePath (Join-Path $out 'summary.json')
if ($LASTEXITCODE -ne 0) { throw 'The complete paired results did not validate.' }
