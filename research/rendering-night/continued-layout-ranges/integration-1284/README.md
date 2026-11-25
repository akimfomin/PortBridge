# Continued #1284 · Layout coalescing compatibility

This is V2 applied to [Continued #1284 at `ddda285799feda76da87c074f6919c493007e90f`](https://github.com/ubiquitarianism/leonida/commit/ddda285799feda76da87c074f6919c493007e90f). The refreshed patch preserves #1284's undo journal and [DadaCap's `5959a09` release and same-layout fix](https://github.com/ubiquitarianism/leonida/commit/5959a09f53223eb26dad2c02da340d8045d66b11). The V2 `pieces()` and `visit()` implementations carry over exactly. At every actual mutation, `set()` still calls `note(id)` before changing the layout.

## Results

The synthetic CPU fixture calls the production `prepare()` and `emit()` helpers with test callbacks. It selects a 16-cell partial image range containing four initially undefined cells. Three ordered commands release the mixed range, explicitly discard it into transfer destination, and transition a smaller range to transfer source. A per-cell oracle checks coverage, old and new layouts, plus synchronization scopes in order. The test explicitly invokes tracker rollback and commit to simulate submit outcomes.

| Check | `ddda2857` | `ddda2857` + V2 |
| --- | ---: | ---: |
| Release barrier records | 12 | 3 |
| Total barrier records | 14 | 5 |
| Ordered enhanced barrier calls | 3 | 3 |
| Release heap allocations, with or without tracker transaction | 5 | 4 |
| Same-layout barrier heap allocations in transaction | 0 | 0 |
| Cancellation restores 48 tracked cells and an untouched second image | Pass | Pass |
| Commit preserves the changed subset through a later rollback | Pass | Pass |

Both upstream controls passed in both arms. This run exercises CPU callbacks on this pinned revision. GPU execution and actual queue-failure injection are outside its scope. Each arm produced the same existing `dispatch_mesh` switch warning with LLVM-MinGW Clang 23.1.6 at `-O0`.

- [Combined fixture log, baseline](evidence/baseline-rollback_coalescing_test.log) · [V2](evidence/candidate-rollback_coalescing_test.log)
- [Texture barrier control, baseline](evidence/baseline-replay_texture_barrier_test.log) · [V2](evidence/candidate-replay_texture_barrier_test.log)
- [State-map control, baseline](evidence/baseline-d3d12_state_map_test.log) · [V2](evidence/candidate-d3d12_state_map_test.log)

## Reproduce on Windows

Use PowerShell in a writable copy of this bundle with a clean working directory. Have an existing Continued checkout that contains the pinned Git object, LLVM-MinGW `clang++` on `PATH`, and the `Vulkan-Headers` include directory from [Khronos commit `6802bb47`](https://github.com/KhronosGroup/Vulkan-Headers/commit/6802bb4733b63ed5efd3adb308a6c885ef180ea1). Provide the two input paths when prompted. The script prepares separate copies of `runtime` and writes build outputs there.

```powershell
$checkout = Read-Host 'Path to the Continued checkout'
$headers = Read-Host 'Path to the Vulkan-Headers include directory'
.\reproduce.ps1 -ContinuedCheckout $checkout -VulkanHeaders $headers
```

The [patch](continued-layout-v2-on-ddda2857.patch) SHA-256 is `42a4f637eb9858dddd3fece84fce8289b980e6f2ca03c7fcd6a4bc7b9acb00ee`. The [fixture](rollback_coalescing_test.cpp) and patch use [GPL-3.0-or-later](LICENSE). [PortBridge](https://github.com/akimfomin/PortBridge)
