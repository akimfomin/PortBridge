# PortBridge rendering and compiler research

Each package pins its receiving project and uses hand-written or source-generated inputs. Each experiment is independent. The original project licenses apply to the patches and fixtures. [GPL-3.0 license](LICENSE.GPL-3.0)

| Project and evidence | Observed desk and hardware result |
| --- | --- |
| [Xbox2Windows #2127 fenced mesh readback](xbox2windows-mesh-readback/REVIEW.md) | Independent RTX readback confirmed three complete 1,024-pixel outputs. A reference with only stale pixels produced all 1,024 expected mismatches. |
| [D3D12 and Vulkan persistence controls](persistent-cache/README.md) | Six balanced D3D12 groups and three Vulkan groups measured replay with normal driver settings at identical or new filenames. Vulkan feedback identifies confirmed application-cache hits. |
| [VIctory #1716 live PHI rings](victory-live-phi/README.md) | On the exact PR head, the largest generated one-seed shader lost 64 PHIs and went from 4,168 to 3,724 bytes. All 12 outputs passed Microsoft DXV; eight smaller before/after GPU cases checked 72 words on RTX 4070 Ti SUPER. |
| [AnyXboxX portable byte packing](anyxboxx-packed-byte/METHOD.md) | The unpatched frontend rejects the opcode. The candidate adds the fixed default mode local to this frontend; all 131,200 bytes from the one-group RTX readback matched independently generated expectations. |
| [AnyXboxX capped disk cache](anyxboxx-disk-pressure/METHOD.md) | Under a full temporary cache, metadata calls halved over 64 inserts. Directory scans were unchanged and separate-writer capacity caveats remain. |
| [Continued replay barriers V2](continued-layout-ranges/README.md) | The synthetic Vulkan A/B retained exact readback for 699,040 texels and reduced 97 transition records to 13 in two unchanged calls. The CPU controls show workload-dependent costs. |
| [Continued #939 on-demand checkpoint](continued-checkpoint-gap/README.md) | A CPU fixture built from the exact public compute branch shows the opt-in checkpoint after slow eager compiles. The first-use path takes a different branch, with no checkpoint request. |

The tests do not cover game data, game startup or frame rate. Independent NVIDIA/AMD repeats and receiver decisions can be tracked in the relevant public discussion.
