param(
    [Parameter(Mandatory)] [string] $Compiler
)

$ErrorActionPreference = 'Stop'
$guardHash = 'F07E7302B85BDCDD66745F283768E60A2E266B6A16847E3234F92D95606C161F'
if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'guard.h')).Hash -ne $guardHash) {
    throw 'Worker guard differs from the reviewed source.'
}
$memory = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
$freeCommit = $memory.CommitLimit - $memory.CommittedBytes
Write-Host "CPU build preflight available_commit=$freeCommit physical_bytes=$($memory.AvailableBytes)"
if ($freeCommit -lt 3GB -or $memory.AvailableBytes -lt 6GB) {
    throw 'Build requires at least 3 GiB available commit and 6 GiB available physical RAM.'
}

$source = Join-Path $PSScriptRoot 'scratch_probe.cpp'
$probe = Join-Path $PSScriptRoot 'scratch_probe.exe'
& $Compiler -std=c++20 -O2 -static -municode -Wall -Wextra -Werror $source -ld3d12 -ldxgi -lpsapi -o $probe
if ($LASTEXITCODE -ne 0) { throw "D3D12 probe build failed with exit code $LASTEXITCODE." }
