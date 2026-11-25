# RTX 4070 Ti SUPER paired replay

Each of eight fresh processes checked 7,056 timed chains on the RTX 4070 Ti SUPER with NVIDIA driver 617.14. Each ran 14 cases, 24 midpoint-selected epochs out of 180 per case, and seven samples per strategy. The three primary processes per API use modeled setup 8 and unit 1. One process per API uses setup 14 as a sensitivity check. The complete capture SHA-256 is `8be3a039ef5957eb571b1fdd749ab112dd8befb540811da2e64b0269e0488502`.

The wall interval starts before planning and ends when the GPU fence completes. It includes staging writes, command recording, one measured submission, a buffer-dependent compute dispatch, and waiting for completion. Warmups, destination restoration, and whole-buffer verification follow separate, untimed paths. Vulkan restores accumulated pre-epoch contents. D3D12 restores a fixed reference buffer. Both verify the complete device buffer and the consumer's output. The originating applications provide the upload patterns. The replay times measure the upload-and-consume chain.

The Vulkan exact arm batches every region in one native `vkCmdCopyBuffer` call. The D3D12 exact arm records the required native `CopyBufferRegion` calls into the same submission. All strategies use the same submission structure within each API. The Vulkan hardware selector rejects all other devices and records a non-host-visible, device-local destination. Exact and per-policy caps are shared.

Vulkan CSV intervals are nanoseconds with 100 ns observable granularity here. Vulkan passes the full interval as `total_ns`; `submit_fence_ns` includes both queueing and GPU execution. D3D12 sample arrays are already in microseconds, in the named order specified by each file. The summaries place the chain, planning, and staging intervals in microseconds. The percentile uses nearest rank. The primary relative metric is 100 × (optimal / baseline − 1) applied to the sum of each selected epoch's median chain time, separately for each process and API. Negative values indicate a shorter chain.

The paired summary checks case and epoch identities and, for each strategy, the same region count, copied bytes and modeled score. Native uncapped and replicated or artificially capped cases appear separately. The desktop GPU was active before and after the replays. Fixed clocks and temperature snapshots do not control that competing workload. Identical-plan controls show large timing variance.

## Replay commands

```powershell
./vulkan_benchmark_reset.exe --adapter rtx4070tisuper --trace open-all.pbtrace --shader consumer_vulkan.spv --frame-limit 24 --samples 7 --setup 8 --unit-cost 1
./d3d12_transfer.exe --hardware --trace open-all.pbtrace --frame-limit 24 --samples 7 --setup 8
```

Start each process separately three times with setup 8 and once with setup 14. Capture standard output and adapter telemetry before and after. Do not set a Vulkan ICD override for the physical run.

The archived raw measurements round-trip to their original bytes. Their hashes are in [the manifest](evidence/raw/SHA256SUMS-uncompressed.txt). The D3D12 adapter LUID fields in the raw output identify the local adapter for a Windows session and are unused by the summary.

## Rebuild summaries

```powershell
$primary = Get-ChildItem evidence/raw/vulkan-rtx4070tisuper-setup8-run*.csv.gz,evidence/raw/d3d12-formal-setup8-r*.json.gz
$sensitivity = Get-ChildItem evidence/raw/vulkan-rtx4070tisuper-setup14-run*.csv.gz,evidence/raw/d3d12-formal-setup14-r*.json.gz
python summarize_physical.py $primary.FullName
python summarize_physical.py $sensitivity.FullName
```
