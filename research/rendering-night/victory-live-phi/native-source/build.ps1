# SPDX-License-Identifier: GPL-3.0-or-later
$ErrorActionPreference = 'Stop'
$vctRepo = Split-Path (Split-Path $PSScriptRoot)
$vctWork = Split-Path $vctRepo
$vctRust = Join-Path $vctWork 'portbridge-lds-pilot/toolchain/rustup/toolchains/stable-x86_64-pc-windows-gnullvm/bin'
$vctLink = Join-Path $vctWork 'Leonida-portable-vulkan/tools/llvm-mingw-20261117-ucrt-x86_64/bin/x86_64-w64-mingw32-clang.exe'
$vctWinRoot = Join-Path $vctWork 'portbridge-night-xcl-target/release/build'
$vctTarget = Join-Path $vctRepo 'target'

& python -I (Join-Path $PSScriptRoot 'prepare_sources.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$vctLib = @(Get-ChildItem -LiteralPath $vctTarget -Recurse -File -Filter 'libvictory_shader-*.rlib')
$vctWin = @(Get-ChildItem -LiteralPath $vctWinRoot -Recurse -File -Filter 'libwindows-*.rlib')
if ($vctLib.Count -ne 1 -or $vctWin.Count -ne 1) {
    throw 'Expected one matching VIctory and Windows rlib'
}
$vctDeps = Get-ChildItem -LiteralPath $vctTarget,$vctWinRoot -Recurse -File -Include '*.rlib','*.dll' |
    Select-Object -ExpandProperty DirectoryName -Unique
$vctArgs = foreach ($vctDir in $vctDeps) { '-L'; "dependency=$vctDir" }
$vctExe = Join-Path $PSScriptRoot 'victory_phi_readback.exe'
$vctPathBefore = $env:PATH
try {
    $env:PATH = "$vctRust;$(Split-Path $vctLink);$vctPathBefore"
    & (Join-Path $vctRust 'rustc.exe') --edition 2024 --target x86_64-pc-windows-gnullvm -D warnings `
        -C "linker=$vctLink" @vctArgs --extern "victory_shader=$($vctLib[0].FullName)" `
        --extern "windows=$($vctWin[0].FullName)" -o $vctExe (Join-Path $PSScriptRoot 'worker.rs') 2>&1 |
        Tee-Object -FilePath (Join-Path $PSScriptRoot 'link.log')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Get-FileHash -LiteralPath $vctExe -Algorithm SHA256
} finally {
    $env:PATH = $vctPathBefore
}
