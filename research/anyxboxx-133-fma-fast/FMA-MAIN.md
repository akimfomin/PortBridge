# FMA rounding on current AnyXboxX main

The CPU double-rounding cases also reproduce on AnyXboxX main `d02eee01bedefedda48204b798df3002c7e2ffcc`. This control uses the six fused opcodes implemented there. The 36 directed opcode cases had 24 disagreements against the float32 one-rounding witnesses before the patch and zero after it. The regular MAC and MAD controls returned the same words before and after. The full local candidate suite reported 462 passed and 203 skipped. Ruff passed. [Exact words](fma-main-focused-results.json)

For baseline and candidate, prepare separate AnyXboxX checkouts at that commit. Apply [the focused patch](fma-main-focused.patch) only to the candidate. Use the Python test environment documented by AnyXboxX (the probe imports their test encoders) and run `python fma_main_focused.py <upstream-checkout>` and `python fma_main_focused.py <candidate-checkout>`. Inputs are synthetic. The changes and fixture follow the receiving GPL-3.0-or-later license. [License](LICENSE.AnyXboxX)

This preserves a separately tested main-base option. The two source files also contain helpers touched by the open [AnyXboxX #133](https://github.com/LooperSalty/AnyXboxX/pull/133). Native RDNA2 rounding is tracked separately in [PortBridge #58](https://github.com/akimfomin/PortBridge/issues/58).
