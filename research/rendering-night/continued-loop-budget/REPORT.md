# Continued loop-budget transfer check

XCL #2034 now counts entry to real loop headers in both forms. The merged correction carries the header role in the compact class key, so the first entry consumes budget and an acyclic branch to a lower address does not. That source change has no direct equivalent in Continued. Continued builds explicit structured SPIR-V loops, initializes each header's visit count to 1 on entry and diverts the back branch to the structured merge when it reaches the limit. [Merged XCL fix and attribution](https://github.com/xcl-dev/xcl/pull/2034#issuecomment-7150370452) · [Continued #1101](https://github.com/ubiquitarianism/leonida/pull/1101)

Continued #1101 head `10ad8809b3ddf9f33c97ff0a52555bffbbb15aa7` and current main at inspection `3ff2a2adcd3517f09d120540ae441c947d422e34` have identical `tools/spirv_loop_guard.py` blob `9036d78157b471bb967fa31cac90ddc44319339c`. Its existing tests check a body store on terminating and unreachable exits, dispatch termination and fresh nested budgets. They do not check an externally visible store after a forced merge for equivalent native and emulated Wave64 translations. [Guard source](https://github.com/ubiquitarianism/leonida/blob/3ff2a2adcd3517f09d120540ae441c947d422e34/tools/spirv_loop_guard.py) · [Existing tests](https://github.com/ubiquitarianism/leonida/blob/3ff2a2adcd3517f09d120540ae441c947d422e34/tests/semantic/test_loop_iteration_guard.py)

## Observable forced exit difference

A finite synthetic program writes its current counter during the loop and writes marker 42 after the loop. The same instructions and per-invocation calculations are used on native Wave64 and emulated Wave64. `boundary_probe.py` checks every lane on the two exact Continued trees using each tree's CPU interpreter. All cases had the same outcomes on both trees.

| Budget / natural visits | Native Wave32 and Wave64 | Emulated Wave64 in two 32-lane halves |
| --- | --- | --- |
| 0 (disabled) / 5 | Count 5, marker 42 | Count 5, marker 42 |
| 1 / 1 | Count 1, marker 42 | Count 1, marker 42 |
| 1 / 3 | Count 1, marker absent | Count 1, marker 42 |
| 4 / 3 or 4 | Count 3 or 4, marker 42 | Count 3 or 4, marker 42 |
| 4 / 5 | Count 4, marker absent | Count 4, marker 42 |

At the forced merge, native64 still has the loop's guest `%pc` and checks it against the post-loop block before running the store. The equivalent emitted emulated64 merge goes directly to that block. Both generated modules at budget 4 with natural exit 5 assembled and validated for Vulkan 1.3. These are CPU and offline module results. They establish a difference in side effects after forced truncation. The project documents the structured merge and undefined new merge inputs without specifying a uniform guarantee about post-loop guest stores, so the receiving author should decide the intended contract. [#1101 log](pr-1101.log) · [Main log](main.log) · [Validated source trace](main-forced-spv-trace.log) · [Documented loop guard](https://github.com/ubiquitarianism/leonida/blob/10ad8809b3ddf9f33c97ff0a52555bffbbb15aa7/docs/design.md#L283)

The finite acyclic guest program with a negative branch offset returned 17 on all lanes with budgets 0 and 1. It generated no `OpLoopMerge`, so no loop counter charged that branch. This distinguishes the reported XCL address-role bug from Continued's emitted structured path.

## SPIR-V layout precondition

Continued's guard identifies a back predecessor using label order. Both handwritten finite layouts in `layout_probe.py` pass Vulkan 1.3 validation. They have the same graph, including two forward predecessors of one loop header. If one of those predecessors appears later in the file, the helper reports two back edges and refuses to instrument it. The only current call path is `rdna2spirv.finish_module()` and its reviewed structured emitters create fresh headers with preceding entry blocks and later latches. The handmade variant is a valid general SPIR-V layout, with no found producer in this translator. [Layout control](layout-control.spvasm) · [Layout result](layout.log) · [SPIR-V control-flow declarations](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html)

## Reproduce

Use Python with source checkouts at the revisions above. Run `python -I proof/boundary_probe.py <checkout>` for each. The workspaces need `tools` and `tests/semantic` from the matching revision. The proof writes only ordinary synthetic interpreter inputs into temporary folders. Run `python -I proof/layout_probe.py <spirv-as> <spirv-val>` with the proof folder under the #1101 checkout to reproduce the separate layout control.
