# D3D12 scratch placement count controls

These two controls use the [16-buffer fixture](../native/README.md) with exactly one or four active 64 KiB scratch resources and the same fixed 1 MiB placed heap. The ordinary committed allocations total 64 KiB or 256 KiB of resource size, respectively. A sparse placed heap may cost more to create and reserves the unused capacity. The check estimates where the creation-time benefit begins for this one workload shape.

The source keeps the original GPU, resource states, aligned offsets, host timing, guarded execution, readback and mirrored order. Both arms check every active byte. The result header includes the active buffer count and placed heap capacity, and the analysis checks both before reading samples.

Run the phases individually when the corresponding slot is available. The instructions below show the one-buffer control. Repeat with `4` and `evidence-4` for the four-buffer control.

```powershell
.\build.ps1 -Compiler 'path\to\clang++.exe' -Buffers 1
New-Item -ItemType Directory -Path .\evidence-1
.\run.ps1 -Stage Verify -LogDirectory .\evidence-1 -Buffers 1
.\run.ps1 -Stage Measure -LogDirectory .\evidence-1 -Buffers 1
python -I -B .\summarize.py .\evidence-1 1
```

The original 16-buffer source, executable and results are in the sibling directory. These controls have separate executables and evidence directories.

## RTX 4070 Ti SUPER result

All guarded workers returned successfully and every active byte matched. With one buffer, the placed path lost five of eight pairs. The median pair was 80.050 µs slower (44.624%). With four buffers the placed path won all eight pairs. The median pair saved 375.100 µs (53.863%). The fixed 1 MiB heap reserves more capacity than the 64 KiB single-buffer and 256 KiB four-buffer committed cases. [1-buffer details](evidence-1/summary.log) · [4-buffer details](evidence-4/summary.log)
