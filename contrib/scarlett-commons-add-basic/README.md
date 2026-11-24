# Scarlett Commons addition case on Continued

This source-only comparison uses the original Scarlett Commons `valu-f32/add-basic` case at `ba9549c254647b9f6ef3b4e47684e69a668b9ec1` and Continued's translator and CPU test helpers at `5496f79f93c41f1134ce4c9e1d2674aa00c6bb55`. [Original case](https://github.com/scarlett-commons/scarlett-commons/blob/ba9549c254647b9f6ef3b4e47684e69a668b9ec1/cases/valu-f32/add-basic.json) · [Continued helpers](https://github.com/ubiquitarianism/leonida/blob/5496f79f93c41f1134ce4c9e1d2674aa00c6bb55/tests/semantic/support.py#L38-L64)

Use Git, Python 3.12, and two clean local checkouts at those revisions. From the PortBridge root, run the following command with your checkout paths.

```text
python -B -I contrib/scarlett-commons-add-basic/compare.py /path/to/scarlett-commons /path/to/continued
```

The harness reads the pinned local inputs and uses temporary files. Scarlett Commons' validator checks the untouched JSON fixture first. Continued then translates its instructions to SPIR-V text and interprets one invocation of a 1 × 1 × 1 workgroup with Wave32 and its synthetic output descriptor. For the control the harness replaces the only addition with subtraction in memory and retains the original expected word.

On Windows with Python 3.12.14, validation reported `1 cases, 0 problems`. The original produced `0x40700000` (3.75). The control produced `0x3f400000` (0.75) and was rejected against `0x40700000`.

The result covers CPU interpretation of one hand-written case. Vulkan execution and the separate-process adapter remain work for the upstream tasks. [Adapter task](https://github.com/scarlett-commons/scarlett-commons/issues/32) · [Vulkan runner task](https://github.com/scarlett-commons/scarlett-commons/issues/6)
