param(
    [Parameter(Mandatory)] [string] $SourceCheckout,
    [Parameter(Mandatory)] [string] $Compiler,
    [Parameter(Mandatory)] [string] $OutputDirectory,
    [switch] $Measure
)

$ErrorActionPreference = 'Stop'
$source = Join-Path (Resolve-Path -LiteralPath $SourceCheckout).Path 'runtime/src'
$clang = (Resolve-Path -LiteralPath $Compiler).Path
$hashes = @{
    stock = '3726dc0725575f2eb4cf2275f4bcb83f878fe4ac124d76925be3eccb97a7c876'
    bounded = '413310380a4a05d330dac7863e4b8eab30cc0b2e8204a636b7c03e9c84827376'
    composed = '2d009b6aeb073815858370babd890ca497b15f0616d1058504e1996b8f096ad3'
}
if ((Get-FileHash -LiteralPath (Join-Path $source 'shader_library.h')).Hash -ne $hashes.stock) {
    throw 'Use the stock Continued 871e4b8 source with LF line endings.'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new output directory.' }
$out = (New-Item -ItemType Directory -Path $OutputDirectory).FullName
$fixtures = Join-Path $out 'fixtures'

function Run-Checked([string] $Program, [string[]] $CommandArgs) {
    & $Program @CommandArgs
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with code $LASTEXITCODE." }
}

function Build-Probe([string[]] $CompileArgs) {
    $memory = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
    if (($memory.CommitLimit - $memory.CommittedBytes) -lt 3GB) {
        throw 'CPU compile admission refused before launching Clang.'
    }
    Run-Checked $clang (@('-std=c++20', '-O2', '-static') + $CompileArgs)
}

Run-Checked python @('-I', (Join-Path $PSScriptRoot 'index_fixture.py'), $fixtures)
$small = Get-Content -Raw -LiteralPath (Join-Path $fixtures 'manifest.json') | ConvertFrom-Json | Select-Object -First 1
foreach ($arm in 'stock', 'bounded', 'composed') {
    $tree = Join-Path $out $arm
    $headers = (New-Item -ItemType Directory -Path (Join-Path $tree 'runtime/src')).FullName
    foreach ($header in 'descriptor_table.h', 'shader_library.h', 'spirv_words.h') {
        Copy-Item -LiteralPath (Join-Path $source $header) -Destination $headers
    }
    if ($arm -ne 'stock') {
        Run-Checked git @('-C', $tree, 'init', '--quiet')
        $patches = @('00-main-only-reference.patch', 'bounded-main-index.patch')
        if ($arm -eq 'composed') { $patches += 'bounded-cursor-short-decimal.patch' }
        foreach ($file in $patches) {
            $patch = Join-Path $PSScriptRoot $file
            $apply = @('-C', $tree, '-c', 'core.autocrlf=false', 'apply', '--include=runtime/src/shader_library.h')
            Run-Checked git ($apply + @('--check', $patch))
            Run-Checked git ($apply + $patch)
        }
    }
    if ((Get-FileHash -LiteralPath (Join-Path $headers 'shader_library.h')).Hash -ne $hashes[$arm]) {
        throw "Header for $arm differs from the measured source."
    }

    $loader = Join-Path $tree 'load.exe'
    Build-Probe @('-I', $headers, '-municode', (Join-Path $PSScriptRoot 'load_probe.cpp'), '-o', $loader, '-lpsapi')
    Run-Checked $loader @((Join-Path $fixtures $small.name), [string]$small.entries, [string]$small.richness)
    Build-Probe @('-I', $headers, (Join-Path $PSScriptRoot 'number_probe.cpp'), '-o', (Join-Path $tree 'number.exe'))
    if ($arm -ne 'stock') {
        Run-Checked $loader @('checks', (Join-Path $fixtures 'controls'))
        $controls = Join-Path $tree 'controls.exe'
        Build-Probe @('-I', $headers, '-DPB_STREAMED', (Join-Path $PSScriptRoot 'stream_controls.cpp'), '-o', $controls)
        Run-Checked $controls @((Join-Path $tree 'cursor-controls'))
    }
}
$controlArgs = @('-I', (Join-Path $PSScriptRoot 'compare.py'), $out)
if ($Measure) { $controlArgs += '--measure' }
Run-Checked python $controlArgs
