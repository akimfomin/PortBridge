param(
    [Parameter(Mandatory)] [string] $Rustc,
    [Parameter(Mandatory)] [string] $Compiler,
    [string] $RustLinker,
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'build')
)

$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a fresh output directory.' }
$real = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
if (($real.CommitLimit - $real.CommittedBytes) -lt 3GB -or $real.AvailableBytes -lt 6GB) {
    throw 'CPU build admission refused below 3 GiB commit or 6 GiB physical.'
}
$common = Split-Path $PSScriptRoot
$planner = Join-Path $PSScriptRoot '../relay_fetch_pack.rs'
$guard = Join-Path $common 'guard.h'
if ((Get-FileHash -LiteralPath $planner).Hash -ne '5664F75E615EFC642F93DA5A6BF8A7047CB8E2062F32EF04B59415AD9061AA8D') {
    throw 'The relay packer differs from the reviewed fork candidate.'
}
if ((Get-FileHash -LiteralPath $guard).Hash -ne 'F07E7302B85BDCDD66745F283768E60A2E266B6A16847E3234F92D95606C161F') {
    throw 'The worker guard differs from the reviewed PortBridge source.'
}
$out = (New-Item -ItemType Directory -Path $OutputDirectory).FullName
$rustArgs = @('--edition=2024','-C','opt-level=2','-D','warnings')
if ($RustLinker) { $rustArgs += '-C', "linker=$RustLinker" }
$emitter = Join-Path $out 'emit-case.exe'
& $Rustc @rustArgs (Join-Path $PSScriptRoot 'emit_case.rs') -o $emitter
if ($LASTEXITCODE -ne 0) { throw 'Exact Rust planner build failed.' }
$descriptor = & $emitter
if ($LASTEXITCODE -ne 0) { throw 'Exact planner controls disagree.' }
$descriptor | Set-Content -LiteralPath (Join-Path $out 'relay-cases.inc') -Encoding ascii
$worker = Join-Path $out 'relay-readback.exe'
& $Compiler -std=c++20 -O2 -static -municode -Wall -Wextra -Werror "-I$out" "-I$common" `
    (Join-Path $PSScriptRoot 'worker.cpp') -ld3d12 -ldxgi -lpsapi -o $worker
if ($LASTEXITCODE -ne 0) { throw 'D3D12 worker build failed.' }
& $worker --cpu
if ($LASTEXITCODE -ne 0) { throw 'Worker source self-check failed.' }
Get-FileHash -LiteralPath $worker | Select-Object -ExpandProperty Hash
