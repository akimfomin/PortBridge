param(
    [Parameter(Mandatory)] [string] $Rustc,
    [Parameter(Mandatory)] [string] $Clang,
    [Parameter(Mandatory)] [string] $ClangCpp,
    [Parameter(Mandatory)] [string] $Dxc,
    [Parameter(Mandatory)] [string] $WindowsRlib,
    [Parameter(Mandatory)] [string[]] $DependencyPaths,
    [Parameter(Mandatory)] [string] $GuardHeaders
)

$ErrorActionPreference = 'Stop'
& python -I (Join-Path (Split-Path $PSScriptRoot) 'prepare.py')
if ($LASTEXITCODE -ne 0) { throw 'Failed to extract the pinned blend inputs.' }
$rust = (Resolve-Path -LiteralPath $Rustc).Path
$linker = (Resolve-Path -LiteralPath $Clang).Path
$cpp = (Resolve-Path -LiteralPath $ClangCpp).Path
$dxcPath = (Resolve-Path -LiteralPath $Dxc).Path
$bindings = (Resolve-Path -LiteralPath $WindowsRlib).Path
$headers = (Resolve-Path -LiteralPath $GuardHeaders).Path
$deps = foreach ($dir in $DependencyPaths) {
    '-L'
    "dependency=$((Resolve-Path -LiteralPath $dir).Path)"
}
$out = Join-Path $PSScriptRoot 'build'
[void](New-Item -ItemType Directory -Path $out -Force)
$shader = Join-Path $PSScriptRoot 'mixed.hlsl'
& $dxcPath -Ges -WX -T vs_6_0 -E vs_main -Fo (Join-Path $out 'vertex.dxil') $shader
if ($LASTEXITCODE -ne 0) { throw 'Synthetic vertex shader build failed.' }
& $dxcPath -Ges -WX -T ps_6_0 -E ps_main -Fo (Join-Path $out 'pixel.dxil') $shader
if ($LASTEXITCODE -ne 0) { throw 'Synthetic pixel shader build failed.' }
& $dxcPath -dumpbin (Join-Path $out 'pixel.dxil') | Set-Content -LiteralPath (Join-Path $out 'pixel-signature.log')
if ($LASTEXITCODE -ne 0) { throw 'Failed to inspect the generated pixel signature.' }

& $rust --edition 2024 --target x86_64-pc-windows-gnullvm -D warnings `
    -C "linker=$linker" @deps --extern "windows=$bindings" -o (Join-Path $out 'uint-blend-worker.exe') `
    (Join-Path $PSScriptRoot 'worker.rs')
if ($LASTEXITCODE -ne 0) { throw 'Native worker build failed.' }
& $cpp -std=c++20 -O2 -Wall -Wextra -Werror -static -municode -I $headers `
    -o (Join-Path $out 'uint-blend-guard.exe') (Join-Path $PSScriptRoot 'job_launcher.cpp') -lpsapi
if ($LASTEXITCODE -ne 0) { throw 'Native job launcher build failed.' }
Get-ChildItem -LiteralPath $out -File | Where-Object Extension -in '.dxil','.exe' | Get-FileHash -Algorithm SHA256
