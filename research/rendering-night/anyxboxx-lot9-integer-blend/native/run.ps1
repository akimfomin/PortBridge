param(
    [Parameter(Mandatory)] [switch] $ApprovedNative,
    [Parameter(Mandatory)] [string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'
if (!$ApprovedNative) { throw 'An allocated native GPU slot is required.' }
$job = Join-Path $PSScriptRoot 'build/uint-blend-guard.exe'
if (!(Test-Path -LiteralPath $job -PathType Leaf)) { throw 'Build the guarded native fixtures first.' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new output directory.' }
$out = (New-Item -ItemType Directory -Path $OutputDirectory).FullName
$adapter = $null
foreach ($arm in 'baseline', 'candidate') {
    $nativeLog = Join-Path $out "$arm-native.log"
    $guardLog = Join-Path $out "$arm-guard.log"
    & $job native $arm $nativeLog | Tee-Object -LiteralPath $guardLog
    if ($LASTEXITCODE -ne 0) { throw "Guard stopped on $arm. Partial logs are in the output directory." }
    $lines = Get-Content -LiteralPath $nativeLog
    $adapterLine = @($lines | Where-Object { $_ -match '^ADAPTER NVIDIA GeForce RTX 4070 Ti SUPER LUID [0-9a-f]{8}:[0-9a-f]{8}$' })
    $resultLine = @($lines | Where-Object { $_ -match "^PSO $arm 0x(?:00000000|80070057)$" })
    if ($adapterLine.Count -ne 1 || $resultLine.Count -ne 1) { throw "Missing native result for $arm." }
    if ($adapter -and $adapter -ne $adapterLine[0]) { throw 'The adapter changed between arms.' }
    $adapter = $adapterLine[0]
    $resultLine[0]
}
