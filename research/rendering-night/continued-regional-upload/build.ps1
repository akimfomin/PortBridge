param(
    [Parameter(Mandatory)] [string] $VulkanInclude,
    [string] $Compiler = 'clang++',
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'build')
)

$ErrorActionPreference = 'Stop'
$include = (Resolve-Path -LiteralPath $VulkanInclude).Path
if (!(Test-Path -LiteralPath (Join-Path $include 'vulkan/vulkan.h') -PathType Leaf)) {
    throw 'VulkanInclude must contain vulkan/vulkan.h'
}
$compilerExe = (Get-Command $Compiler -CommandType Application | Select-Object -First 1).Path
$upstream = Join-Path $PSScriptRoot 'upstream'
$lock = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'upstream-headers.json') | ConvertFrom-Json
if ($lock.commit -ne '0bc810504aa44ba7e30f3c3352ebad697b9814d6' -or $lock.files.Count -ne 14) {
    throw 'Continued source manifest differs'
}
foreach ($entry in $lock.files) {
    if ($entry.path -notmatch '^(LICENSE|runtime/(src|shims|test)/[a-zA-Z0-9_.]+\.(h|md))$') {
        throw 'Unexpected path in Continued source manifest'
    }
    $actual = (Get-FileHash -LiteralPath (Join-Path $upstream $entry.path)).Hash
    if ($actual -ne $entry.sha256) { throw "Pinned source hash mismatch for $($entry.path)" }
}
$guardHash = 'F07E7302B85BDCDD66745F283768E60A2E266B6A16847E3234F92D95606C161F'
if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'guard.h')).Hash -ne $guardHash) {
    throw 'Bundled worker guard differs from the reviewed source'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new build directory' }
[void](New-Item -ItemType Directory -Path $OutputDirectory)
$output = (Resolve-Path -LiteralPath $OutputDirectory).Path
$memory = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
if (($memory.CommitLimit - $memory.CommittedBytes) -lt 3GB) {
    throw 'CPU build needs at least 3 GiB of available system commit'
}
& $compilerExe -std=c++20 -O2 -static -pthread -municode -D_WIN32_WINNT=0x0A00 `
    "-I$PSScriptRoot" "-I$upstream/runtime/src" "-I$upstream/runtime/shims" "-I$upstream/runtime/test" `
    -isystem $include (Join-Path $PSScriptRoot 'texture_readback.cpp') `
    -o (Join-Path $output 'texture-readback.exe') -lpsapi
if ($LASTEXITCODE) { throw "Native worker compile failed ($LASTEXITCODE)" }
Get-FileHash -LiteralPath (Join-Path $output 'texture-readback.exe')
