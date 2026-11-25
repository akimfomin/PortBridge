# SPDX-License-Identifier: MIT
param(
    [Parameter(Mandatory)] [string] $VulkanInclude,
    [string] $Compiler = 'clang++',
    [string] $SpirvAs = 'spirv-as',
    [string] $SpirvVal = 'spirv-val',
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'build')
)

$ErrorActionPreference = 'Stop'
$include = (Resolve-Path -LiteralPath $VulkanInclude).Path
if (!(Test-Path -LiteralPath (Join-Path $include 'vulkan/vulkan.h') -PathType Leaf)) {
    throw 'VulkanInclude must contain vulkan/vulkan.h'
}
$compilerExe = (Get-Command $Compiler -CommandType Application | Select-Object -First 1).Path
$assemblerExe = (Get-Command $SpirvAs -CommandType Application | Select-Object -First 1).Path
$validatorExe = (Get-Command $SpirvVal -CommandType Application | Select-Object -First 1).Path
$guardHash = 'F07E7302B85BDCDD66745F283768E60A2E266B6A16847E3234F92D95606C161F'
if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'guard.h')).Hash -ne $guardHash) {
    throw 'Bundled worker guard differs from the reviewed source'
}

function Check-AvailableCommit {
    $memory = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
    if (($memory.CommitLimit - $memory.CommittedBytes) -lt 3GB) {
        throw 'CPU build needs at least 3 GiB of available system commit'
    }
}

Check-AvailableCommit
& python -I -B (Join-Path $PSScriptRoot 'prepare.py') --output $OutputDirectory `
    --assembler $assemblerExe --validator $validatorExe
if ($LASTEXITCODE) { throw "SPIR-V assembly or validation failed ($LASTEXITCODE)" }
$output = (Resolve-Path -LiteralPath $OutputDirectory).Path
Check-AvailableCommit
& $compilerExe -std=c++20 -O2 -Wall -Wextra -Werror -Wno-missing-field-initializers -Wformat=2 `
    -D_WIN32_WINNT=0x0A00 -static -municode "-I$include" "-I$output" `
    (Join-Path $PSScriptRoot 'readback.cpp') -o (Join-Path $output 'readback.exe') -lpsapi
if ($LASTEXITCODE) { throw "Native worker compile failed ($LASTEXITCODE)" }
Get-FileHash -LiteralPath (Join-Path $output 'readback.exe')
