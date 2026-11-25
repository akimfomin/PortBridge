param(
    [Parameter(Mandatory)] [string] $ContinuedCheckout,
    [Parameter(Mandatory)] [string] $VulkanHeaders,
    [string] $Compiler = 'clang++'
)

$ErrorActionPreference = 'Stop'
$pin = 'ddda285799feda76da87c074f6919c493007e90f'
$checkout = (Resolve-Path -LiteralPath $ContinuedCheckout).Path
$headers = (Resolve-Path -LiteralPath $VulkanHeaders).Path
$clang = (Get-Command $Compiler -CommandType Application).Source

Push-Location -LiteralPath $PSScriptRoot
try {
    $build = 'reproduction'
    if (Test-Path -LiteralPath $build) { throw 'Use a fresh bundle copy to reproduce again.' }
    [void](New-Item -ItemType Directory -Path $build)
    $archive = Join-Path (Resolve-Path -LiteralPath $build) 'runtime.zip'
    $patch = (Resolve-Path -LiteralPath 'continued-layout-v2-on-ddda2857.patch').Path
    & git -C $checkout archive --format=zip "--output=$archive" $pin runtime
    if ($LASTEXITCODE -ne 0) { throw 'The checkout does not contain the pinned runtime tree.' }

    foreach ($arm in 'baseline', 'candidate') {
        $root = Join-Path $build $arm
        Expand-Archive -LiteralPath $archive -DestinationPath $root
        if ($arm -eq 'candidate') {
            & git -C $root init --quiet
            if ($LASTEXITCODE -ne 0) { throw 'Candidate scratch initialization failed.' }
            & git -C $root -c core.autocrlf=false apply --check $patch
            if ($LASTEXITCODE -ne 0) { throw 'Patch check failed.' }
            & git -C $root -c core.autocrlf=false apply $patch
            if ($LASTEXITCODE -ne 0) { throw 'Patch application failed.' }
        }
        $cases = [ordered]@{
            rollback_coalescing_test = 'rollback_coalescing_test.cpp'
            replay_texture_barrier_test = "$root/runtime/test/replay_texture_barrier_test.cpp"
            d3d12_state_map_test = "$root/runtime/test/d3d12_state_map_test.cpp"
        }
        $flags = @('-std=c++20', '-O0', '-static', '-pthread', '-DWIN32_LEAN_AND_MEAN', '-DNOMINMAX',
            '-isystem', $headers, '-I', "$root/runtime/src")
        foreach ($test in $cases.Keys) {
            $exe = "$root/$test.exe"
            & $clang @flags $cases[$test] -o $exe
            if ($LASTEXITCODE -ne 0) { throw "Build failed for $arm $test." }
            & "./$exe" $arm | Tee-Object -LiteralPath "$root/$test.log"
            if ($LASTEXITCODE -ne 0) { throw "Test failed for $arm $test." }
        }
    }
} finally {
    Pop-Location
}
