# Scheduler review

Reviewed `507029d1ea8dc65f1fabb68739605d6821843bf1` and its local candidate.

- **Claim ownership.** The queue mutex protects the fresh index and deferred entries. Each `take()` advances the fresh index or removes one deferred head. A retry holds one movable ticket. A changed estimate releases it before classification and can rejoin the tail. The CPU tests exercise growth, a second deferral and a later shrink to the small path.
- **Lock order.** Admission takes the queue mutex and then the gate mutex. The gate releases a ticket using only its own mutex. The worker destroys the ticket before its next `take()`. After the fresh range is exhausted, one waiter keeps its turn at the deferred head while the gate condition releases its own mutex. A small job already claimed uses the `estimate == 0` path without acquiring the queue mutex.
- **Fairness.** A fresh large job joins an existing deferred queue. Its estimate cannot pass an older deferred head. Once a deferred item owns a permit, the OS can run worker threads in either order. For a batch with stable file sizes and finite running jobs, every deferred head either fits alongside existing work or goes next alone when the gate drains. A reclassified input joins a new position.
- **Special modes.** `--large-parallel 1` and the unknown-memory fallback select the original shared/exclusive gate. `--large-module-bytes 0` uses the original atomic index route. Unrestricted available budget grants from the fresh sequence without deferring. A saturating estimate and subtraction-based admission comparison keep the arithmetic safe for an oversized reservation.
- **Related work.** The live #1391 and #1209 hunks are in child-launch memory limits, CLI setup and isolation docs. Neither changes worker admission, the budget gate or its test. The patch does share the checker and documentation files with those PRs. [Windows #1391](https://github.com/ubiquitarianism/leonida/pull/1391) · [Linux #1209](https://github.com/ubiquitarianism/leonida/pull/1209)

## Before and after

`production_regression.py` extracts the verbatim worker loop's selection statements and its gate block from each tree. It also copies the real gate header. The fixture supplies two dummy file sizes and observes the instant a blocking wait is reached. Before releasing an initial permit, the test requires the new worker to enter its exhausted-queue wait. This gives an ordered observation without a sleep and keeps the scope on CPU admission.

| Scenario | Baseline | Candidate |
| --- | --- | --- |
| Budget saturated, large item first on input | Fails the progress assertion. Wait comes first, then jobs `0, 1`. | Passes. Small starts first, then capacity returns and job `0` runs. |
| Budget available | Jobs `0, 1, 2`, pass | Jobs `0, 1, 2`, pass |
| Gate disabled | Jobs `0, 1, 2`, pass | Jobs `0, 1, 2`, pass |
| Exclusive large mode | Large holds the exclusive lock and small holds the shared lock, pass | Same lock assertions and order, pass |

All fixtures return their permits. The registered `large_module_gate_test` also passes the FIFO and reclassification regressions and the existing concurrent admission control. Shader driver timing and optimizer behavior are outside this fixture.

From the isolated root, set `$compiler` to the Clang C++ executable and run `python -I -B local-verification/production_regression.py $compiler`. `production-regression.json` records the exact baseline and candidate exits and observations.
