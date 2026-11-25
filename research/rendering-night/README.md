# PortBridge rendering and compiler research

Each package pins its receiving project and uses hand-written or source-generated inputs. Each experiment is independent. The original project licenses apply to the patches and fixtures. [GPL-3.0 license](LICENSE.GPL-3.0)

| Project and evidence | Observed desk and hardware result |
| --- | --- |
| [VIctory #1716 live PHI rings](victory-live-phi/README.md) | On the exact PR head, the largest generated one-seed shader lost 64 PHIs and went from 4,168 to 3,724 bytes. All 12 outputs passed Microsoft DXV; eight smaller before/after GPU cases checked 72 words on RTX 4070 Ti SUPER. |
| [AnyXboxX portable byte packing](anyxboxx-packed-byte/METHOD.md) | The unpatched frontend rejects the opcode. The candidate adds the fixed default mode local to this frontend; all 131,200 bytes from the one-group RTX readback matched independently generated expectations. |
| [AnyXboxX capped disk cache](anyxboxx-disk-pressure/METHOD.md) | Under a full temporary cache, metadata calls halved over 64 inserts. Directory scans were unchanged and separate-writer capacity caveats remain. |
| [Continued #939 on-demand checkpoint](continued-checkpoint-gap/README.md) | A CPU fixture built from the exact public compute branch shows the opt-in checkpoint after slow eager compiles. The first-use path takes a different branch, with no checkpoint request. |

The tests do not cover game data, game startup or frame rate. Independent NVIDIA/AMD repeats and receiver decisions can be tracked in the relevant public discussion.
