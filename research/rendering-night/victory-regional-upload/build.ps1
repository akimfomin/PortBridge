param(
    [Parameter(Mandatory)] [string] $Rustc,
    [Parameter(Mandatory)] [string] $Compiler,
    [string] $RustLinker,
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'build')
)

$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new output directory.' }
$out = (New-Item -ItemType Directory -Path $OutputDirectory).FullName
$memory = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
if (($memory.CommitLimit - $memory.CommittedBytes) -lt 3GB) {
    throw 'CPU build requires at least 3 GiB of available system commit.'
}
if ((& git hash-object (Join-Path $PSScriptRoot 'texture.rs')) -ne 'a1f72e4383b3584c74e217998723d4ed0249e4e6') {
    throw 'Texture source does not match the pinned victory-fork blob.'
}
if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'guard.h')).Hash -ne 'F07E7302B85BDCDD66745F283768E60A2E266B6A16847E3234F92D95606C161F') {
    throw 'Worker guard differs from the reviewed source.'
}

$rustArgs = @('--edition=2024', '-C', 'opt-level=2', '-D', 'warnings')
if ($RustLinker) { $rustArgs += '-C', "linker=$RustLinker" }
$proof = Join-Path $out 'proof.exe'
& $Rustc @rustArgs --test (Join-Path $PSScriptRoot 'proof.rs') -o $proof
if ($LASTEXITCODE -ne 0) { throw 'Copy planner compile failed.' }
& $proof --nocapture --test-threads=1
if ($LASTEXITCODE -ne 0) { throw 'Copy planner or its upstream checks failed.' }
$emitter = Join-Path $out 'emit-case.exe'
& $Rustc @rustArgs (Join-Path $PSScriptRoot 'emit_case.rs') -o $emitter
if ($LASTEXITCODE -ne 0) { throw 'Fixture emitter compile failed.' }
$fixture = & $emitter
if ($LASTEXITCODE -ne 0) { throw 'Fixture emitter failed.' }
$fixture | Set-Content -LiteralPath (Join-Path $out 'copy-case.inc') -Encoding ascii
& $Compiler -std=c++20 -O2 -static -municode -Wall -Wextra -Werror "-I$out" `
    (Join-Path $PSScriptRoot 'native-upload.cpp') -ld3d12 -ldxgi -lpsapi -o (Join-Path $out 'native-upload.exe')
if ($LASTEXITCODE -ne 0) { throw 'D3D12 worker compile failed.' }
