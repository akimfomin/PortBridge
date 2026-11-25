# XCL direct DXIL research, 25 November 2026

Two separately scoped experiments use source-generated programs on `20cf13022f764208384c610c2ae6a3f4eed201a2`. Each patch applies independently to `80f4819098e921f2e1ab371144d4832f68ffedd6`. The original license is GPL-2.0-only.

- [Compact dominators](dominance/README.md) reduces costly graph tails and produces byte-identical outputs in both the designed and independent synthetic inputs.
- [Redundant live PHI cycles](scc/README.md) reduces container size on an actual synthetic source frontend case. Readback passed on RTX 4070 Ti SUPER for native Wave32 and split Wave64. Two-seed controls preserve behavior.

These are reproducible compiler research candidates. They are separate from the earlier [PHI worklist experiment](https://github.com/xcl-dev/xcl/issues/1269#issuecomment-7146205052). [PortBridge](https://github.com/akimfomin/PortBridge) identified related experiments and tracked scope and evidence across XCL, Continued and VIctory.
