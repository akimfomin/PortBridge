# Draft for KretliJ · Frame-time chart counts submission wait twice

While following up on your PortBridge measurements in [victory-fork #470](https://github.com/fxceless/victory-fork/issues/470#issuecomment-7152241891), I checked the chart on `0d7631e`. Its grey remainder subtracts preparation and copy-back from the measured frame time. The stack then adds preparation, copy-back and the GPU-labelled time. With positive segments the full height becomes `frame time + GPU-labelled time`, even when the stages are disjoint.

In a synthetic 50 ms sample, `redraw()` passed 70 ms of bar height to the canvas. The attached patch draws a 50 ms bar and places independent colored markers on the same scale. With relay enabled, the fork's GPU-labelled value can count a caller waiting for copy-back to finish, so the marker and verdict call it “submit wait”. The colors, frame history and parsed values are preserved. [Monitor source](https://github.com/KretliJ/victory-monitor/blob/0d7631e633f5955269ba9de0154439da9b93f156/victory_monitor.py#L989-L1007) · [Relay wait source](https://github.com/fxceless/victory-fork/blob/2119b0e44c53aa9648307b0c5c73590290305b1f/crates/victory-gpu/src/host.rs#L2296-L2319) · [PortBridge](https://github.com/akimfomin/PortBridge)

The patch applies to `0d7631e633f5955269ba9de0154439da9b93f156`. Five headless tests exercised the actual old and patched redraw methods. The cases cover a disjoint timing example, equal overlapping markers, a counter above frame time, the last 240 samples in a narrow canvas, and unchanged parsing and aggregation. This check used a recording canvas without launching Tk or a title.

## Reproduce locally

`stage_monitor.py` downloads or reuses the three exact public source files and checks their Git blob IDs. The chart test loads the original and patched redraw methods from source. The included upstream license is MIT, copyright KretliJ 2026. [Pinned license](https://github.com/KretliJ/victory-monitor/blob/0d7631e633f5955269ba9de0154439da9b93f156/LICENSE)

```powershell
python stage_monitor.py
git -C upstream apply --check --whitespace=error-all ../victory-monitor-nonadditive-chart.patch
python chart_checks.py
```
