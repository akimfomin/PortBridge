param (
    [Parameter(Mandatory)][string] $Output,
    [Parameter(Mandatory)][string] $Adapter
)

$ErrorActionPreference = 'Stop'
$exe = Join-Path $Output 'validate-rank.exe'
$filter = Join-Path $Output 'rank_filter.spv'
$observe = Join-Path $Output 'rank_observe.spv'
foreach ($case in 'sparse', 'dense', 'empty', 'boundary', 'single') {
    "Fixture $case"
    & $exe $filter $observe (Join-Path $Output "$case.txt") $Adapter
    if ($LASTEXITCODE) { throw "Fixture $case failed" }
}
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $negative = (& $exe $filter $observe (Join-Path $Output 'sparse.txt') $Adapter --physical-index 2>&1 | Out-String).Trim()
    $code = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previous
}
$negative
if ($code -ne 1 -or $negative -notmatch 'second mask differs') {
    throw 'Negative control did not fail in the second mask as expected.'
}
'Physical-index mutation correctly rejected.'
