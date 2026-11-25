param(
    [Parameter(Mandatory)] [string] $Rustc,
    [Parameter(Mandatory)] [string] $Compiler,
    [string] $RustLinker,
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'build')
)

$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new output directory.' }
$memory = Get-CimInstance Win32_PerfRawData_PerfOS_Memory
if (($memory.CommitLimit - $memory.CommittedBytes) -lt 3GB) {
    throw 'CPU build requires at least 3 GiB of available system commit.'
}
$common = Join-Path $PSScriptRoot '../portbridge-victory-dirty-tile-upload'
$sources = @{
    'texture.rs' = '7322F9B183762DD743C9AB423721A446D04938D4FF3AF7C52ACCF49DF00A02EA'
    'copy_plan.rs' = 'FB272EF132E97BC0A7E6CABA2EC5E414415580FEBA84407B3D0CA9A48A5DB063'
    'guard.h' = 'F07E7302B85BDCDD66745F283768E60A2E266B6A16847E3234F92D95606C161F'
}
foreach ($item in $sources.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath (Join-Path $common $item.Key)).Hash -ne $item.Value) {
        throw "Reviewed source differs: $($item.Key)"
    }
}
$out = (New-Item -ItemType Directory -Path $OutputDirectory).FullName
$rustArgs = @('--edition=2024', '-C', 'opt-level=2', '-D', 'warnings')
if ($RustLinker) { $rustArgs += '-C', "linker=$RustLinker" }
$emitter = Join-Path $out 'emit-case.exe'
& $Rustc @rustArgs (Join-Path $PSScriptRoot 'emit_case.rs') -o $emitter
if ($LASTEXITCODE -ne 0) { throw 'Fixture emitter compile failed.' }
$fixture = & $emitter
if ($LASTEXITCODE -ne 0) { throw 'Planner result or address oracle failed.' }
$fixture | Set-Content -LiteralPath (Join-Path $out 'copy-case.inc') -Encoding ascii

$worker = Join-Path $out 'native-bc7.exe'
$compilerArgs = @(
    '-std=c++20', '-O2', '-static', '-municode', '-Wall', '-Wextra', '-Werror',
    "-I$out", "-I$common", (Join-Path $PSScriptRoot 'native-upload.cpp'),
    '-ld3d12', '-ldxgi', '-lpsapi', '-o', $worker
)
& $Compiler @compilerArgs
if ($LASTEXITCODE -ne 0) { throw 'D3D12 worker compile failed.' }
& $worker --cpu
if ($LASTEXITCODE -ne 0) { throw 'BC7 block source control failed.' }
