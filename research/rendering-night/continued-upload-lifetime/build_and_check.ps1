param(
    [Parameter(Mandatory)] [string] $Compiler,
    [Parameter(Mandatory)] [string] $VulkanInclude,
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'build')
)

$ErrorActionPreference = 'Stop'
$compilerExe = (Resolve-Path -LiteralPath $Compiler).Path
$include = (Resolve-Path -LiteralPath $VulkanInclude).Path
$build = $OutputDirectory
if (Test-Path -LiteralPath $build) { throw 'Use a new build directory' }
[void](New-Item -ItemType Directory -Path $build)
& python -I -B (Join-Path $PSScriptRoot 'prepare_extract.py')
if ($LASTEXITCODE) { throw 'Pinned source extraction failed' }
$generated = Join-Path $PSScriptRoot 'generated'
$source = Join-Path $PSScriptRoot 'transport_fixture.cpp'

foreach ($arm in 'stock', 'candidate') {
    $m = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
    if (($m.CommitLimit - $m.CommittedBytes) -lt 3GB -or $m.AvailableBytes -lt 6GB) {
        throw 'CPU build admission refused'
    }
    $defs = @(if ($arm -eq 'candidate') { '-DPB_CANDIDATE' })
    $exe = Join-Path $build "$arm.exe"
    & $compilerExe -std=c++20 -O2 -static -Wall -Wextra -Werror -Wno-missing-field-initializers `
        "-I$generated" -isystem $include @defs $source -o $exe
    if ($LASTEXITCODE) { throw "Fixture compile failed for $arm ($LASTEXITCODE)" }
}

foreach ($arm in 'stock', 'candidate') {
    $exe = Join-Path $build "$arm.exe"
    $log = Join-Path $build "$arm.log"
    & $exe --require-safe-reuse 2>&1 | Tee-Object -LiteralPath $log
    $expected = if ($arm -eq 'stock') { 1 } else { 0 }
    if ($LASTEXITCODE -ne $expected) {
        throw "Unexpected result for $arm ($LASTEXITCODE, expected $expected)"
    }
}
