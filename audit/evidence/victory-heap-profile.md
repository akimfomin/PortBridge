# Compare indexed-texture work on spk-c's VIctory fork

spk-c reported a slow interval of 370.6 ms/frame while driving, with 171.1 ms attributed to the indexed-texture pass. The timings can overlap. The report gives a candidate for profiling. [Original result](https://github.com/fxceless/victory-fork/issues/1418#issuecomment-7207254719)

## One controlled comparison

Use one build from `0211f7925775499770bcaed2ee896ea90e71e449`. Set `VICTORY_HEAP_PROFILE=1` for both runs and change only `VICTORY_TEXTURE_FRAME_BUDGET` between `0` and `1`. Keep the same route, save, camera, image settings and warmed-cache conditions. Use the same `VICTORY_TEXTURE_SLICE_MS` setting in both runs. Start with one pair of warm driving windows. A second pair in reversed order can help distinguish an order effect. Keep show-through, missing textures, stalls and crashes with the run outcome. The frame budget can leave work queued, so faster frames still need comparable draws, dropped draws, queue backlog and the same visible scene. [Switch and budget](https://github.com/spk-c/victory-fork/blob/0211f7925775499770bcaed2ee896ea90e71e449/crates/victory-gpu/src/texture_budget.rs#L19-L54) · [Existing timings](https://github.com/spk-c/victory-fork/blob/0211f7925775499770bcaed2ee896ea90e71e449/crates/victory-gpu/src/host.rs#L10211-L10238)

Clip each log locally to its warm driving interval before running the comparison. Exclude menus, transitions and idle time. Include multiple ordinary frame summaries as well as the detailed phase rows. The script reports medians of emitted samples. Frame summaries use a different sampling cadence from the detailed phase rows. The script reports them separately and does not sum timings. Retain the build, capture settings, hardware and order. Share just the aggregates and the visual outcome.

```text
python audit/evidence/victory-heap-profile.py off.txt on.txt
```

The script was checked against matching synthetic rows, including a faster case with 5,100 → 350 draws and an incomplete capture that exits with status 2. No physical data was produced for this comparison on our occupied GPU. [Why the draw control matters, by dodo4154](https://github.com/fxceless/victory-fork/issues/1417#issuecomment-7207137434)
