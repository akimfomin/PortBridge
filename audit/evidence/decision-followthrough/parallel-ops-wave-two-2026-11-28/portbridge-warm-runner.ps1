if ($env:VICTORY_TEST_WARM_PARENT -ne 'child sentinel') {
    throw 'The synthetic runner did not receive the requested environment.'
}
Add-Content -LiteralPath $env:VICTORY_TEST_WARM_TRACE -Value ($args -join '|')
$global:LASTEXITCODE = if ($args[0] -eq 'warm') { [int]$env:VICTORY_TEST_WARM_EXIT } else { 0 }
