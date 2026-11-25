param(
    [Parameter(Mandatory)] [string] $Rustc,
    [Parameter(Mandatory)] [string] $Clang,
    [Parameter(Mandatory)] [string] $WindowsRlib,
    [Parameter(Mandatory)] [string[]] $DependencyPaths
)

$ErrorActionPreference = 'Stop'
& python -I (Join-Path $PSScriptRoot 'prepare.py')
if ($LASTEXITCODE -ne 0) { throw 'Fixture preparation failed.' }

$rust = (Resolve-Path -LiteralPath $Rustc).Path
$linker = (Resolve-Path -LiteralPath $Clang).Path
$bindings = (Resolve-Path -LiteralPath $WindowsRlib).Path
$deps = foreach ($dir in $DependencyPaths) {
    '-L'
    "dependency=$((Resolve-Path -LiteralPath $dir).Path)"
}

foreach ($arm in 'baseline', 'candidate') {
    $dir = Join-Path $PSScriptRoot "ab/$arm"
    $exe = Join-Path $dir 'descriptor-check.exe'
    $variant = @()
    if ($arm -eq 'candidate') { $variant = @('--cfg', 'pb_candidate') }
    & $rust --edition 2024 --target x86_64-pc-windows-gnullvm --test -D warnings `
        -C "linker=$linker" @deps --extern "windows=$bindings" @variant -o $exe (Join-Path $dir 'fixture.rs')
    if ($LASTEXITCODE -ne 0) { throw "Build failed for $arm." }
    & $exe --test-threads=1 --nocapture | Tee-Object -LiteralPath (Join-Path $dir 'test.log')
    if ($LASTEXITCODE -ne 0) { throw "Descriptor checks failed for $arm." }
}
