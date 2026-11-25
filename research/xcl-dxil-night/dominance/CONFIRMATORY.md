# Longer paired XCL check

The same two release executables and the fixed 24-program BetterJdue synthetic corpus were compared across 40 paired process rounds. Binary hashes and the output container hash are in the data. One separate validation round preceded timing. Every DXIL output remained byte-identical across the timed rounds and control. No source inputs or branch changes since the eight-pair exploratory run.

We calculated the candidate/baseline ratio per fixture within each round, averaged log ratios over the 24 fixtures and back-transformed the overall mean. The candidate used 1.78% less translation time. A paired bootstrap resampled whole process pairs, keeping all fixtures together. Its 95% interval spans 1.33–2.22% improvement. The median per-fixture paired improvement was 2.02%. This interval describes repeat-to-repeat uncertainty for this fixed corpus on this host; it provides no estimate of variation across real shaders or PCs.

[Raw timing samples](campaign-compact-confirmatory-40.json) · [Summary and exact hashes](campaign-compact-confirmatory-interval.json) · [Analysis script](campaign_uncertainty.py)
