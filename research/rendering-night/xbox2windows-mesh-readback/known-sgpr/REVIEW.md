# Statically known SGPR selectors for Xbox2Windows #2127

This local follow-up is based on Leyukaka’s exact head `2dc58a8bdf7e6ed8f4ff2ca4a2f5463c2f34c4d0`. It extends the existing bounded mesh lane-spill path to select a lane from an SGPR whose value is known along the modeled path. The selector uses the bottom six bits of the saved scalar word. Unknown or shader-runtime selectors produce a refusal. Reading a pending selector still requires its wait. The inline selector rules and the runtime-geometry refusal are part of the underlying patch. [Upstream PR](https://github.com/R0Y00/Xbox2Windows/pull/2127) · [AMD RDNA 2 ISA](https://www.amd.com/content/dam/amd/en/documents/radeon-tech-docs/instruction-set-architectures/rdna2-shader-instruction-set-architecture.pdf)

Before the extension, the regression stopped on the first known SGPR selector. With the extension, the spill test recovered all expected words and passed the unknown, runtime-valued, and pending-selector controls. The existing dynamic mesh, dynamic geometry, and amplification refusal tests also passed. [CPU run](green.txt)

| Source-built program | Recovered EXEC words (low, high) | CPU vertex depth | Expected image |
| --- | --- | --- | --- |
| Both inactive slots restored | `1`, `0x100` | +0.5 | 1,024 green pixels |
| Write zero to low slot | `0`, `0x100` | −0.5 | 1,024 clear pixels |
| Write zero to high slot | `1`, `0` | −0.5 | 1,024 clear pixels |

LLVM MC 23.1.6 assembled and decoded the original gfx1013 Wave64 programs with real SGPR selector encodings. A separate control verified that `0x48` and `0x68` selected the same lanes as `8` and `40`. The dynamic-selector program read its selector from a synthetic constant buffer and received the expected refusal. DXC produced the same byte sequences as those used for the prior RTX inline-selector readback, including all render reference files. The extension’s evidence is CPU and DXIL equivalence. The hardware run belongs to the earlier inline-selector review. [Encoded proof](encoded-proof.txt)

```sh
python -B tests/mesh_lane_spill_check.py
python -B tests/mesh_dynamic_aot_check.py
python -B tests/mesh_dynamic_geometry_check.py
python -B tests/mesh_amplification_refusal_check.py
```
