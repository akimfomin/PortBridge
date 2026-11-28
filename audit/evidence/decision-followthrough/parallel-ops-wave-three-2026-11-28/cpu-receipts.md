# Synthetic CPU receipts

All commands ran on Windows in isolated temporary folders. No GPU/native driver coverage is inferred from these receipts.

## Reproduce external source-only suites

- At [Continued 53bc0e3a](https://github.com/ProjectLeonida/mandy/commit/53bc0e3a88bbfc336c8270ae03ad8f3e0fc851b3), obtain only `scripts/run_semantic_tests.py` and `tests/test_run_semantic_tests.py` in the original root layout. Run `python -I tests/test_run_semantic_tests.py` from the root. Expect 28 pass and one platform skip. A child fixture intentionally prints a failing test containing `boom-msg`; the outer result is pass.
- At [KLBF 3206d075](https://github.com/PastiiJay/klbf-lab/commit/3206d075baea85534b2dcc1f73487389d7ae0b35), obtain the source-only `tools/fps-session.py` and `tools/test_fps_session.py`. From their root run `python -I -m unittest discover -s tools -v`. Expect four pass.
- From [AnyXboxX 512099cd](https://github.com/LooperSalty/AnyXboxX/commit/512099cd752c7c07a19b60667a460af602b547e8), obtain only `PrototypeScarlett/emu/shader_cache.py`. Put it under `any/PrototypeScarlett/emu/shader_cache.py` alongside the PortBridge test script and run `python -I test_atomic_cache_publication.py`. The four tests use local, synthetic container labels and mocked sharing failures. They do not run the authors' GPU/translator stack.
- Run `python -I test_f16_midpoint.py` for the CPU numerical check (two tests). The [independent GPU report](https://github.com/R0Y00/Xbox2Windows/pull/3220#issuecomment-7231716533) was from Xbox2Windows only.
- Run `python -I test_keep_ahead.py` for the VIctory-RDNA byte-window model (three tests). It tests small representable ranges, without modeling real GPU synchronization or alias translation.

## Raw synthetic output

```text
..........F..
======================================================================
FAIL: test_a (test_f.T.test_a)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<synthetic fixture>/test_f.py", line 3, in test_a
    def test_a(self): self.assertEqual(1, 2, 'boom-msg')
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 1 != 2 : boom-msg

----------------------------------------------------------------------
Ran 3 tests in 0.000s

FAILED (failures=1)
..
----------------------------------------------------------------------
Ran 2 tests in 0.000s

OK
..........s........
----------------------------------------------------------------------
Ran 29 tests in 7.701s

OK (skipped=1)

test_bench_fallback_cuts_300_seconds_and_is_not_certified (test_fps_session.SessionReportTests.test_bench_fallback_cuts_300_seconds_and_is_not_certified) ... ok
test_bench_window_uses_fractional_timestamps (test_fps_session.SessionReportTests.test_bench_window_uses_fractional_timestamps) ... ok
test_reported_statistics (test_fps_session.SessionReportTests.test_reported_statistics) ... ok
test_wrapped_records_keep_their_timestamp_and_original_file_hash (test_fps_session.SessionReportTests.test_wrapped_records_keep_their_timestamp_and_original_file_hash) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.649s

OK

test_different_peer_is_preserved_and_reported (__main__.PublishChecks.test_different_peer_is_preserved_and_reported) ... ok
test_identical_peer_is_a_hit (__main__.PublishChecks.test_identical_peer_is_a_hit) ... ok
test_retry_publishes_bytes_readable_by_a_fresh_instance (__main__.PublishChecks.test_retry_publishes_bytes_readable_by_a_fresh_instance) ... ok
test_sharing_failure_without_peer_does_not_publish (__main__.PublishChecks.test_sharing_failure_without_peer_does_not_publish) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.022s

OK

test_exact_controls (__main__.ExpMidpoint.test_exact_controls) ... ok
test_rounding_twice_changes_the_midpoint_result (__main__.ExpMidpoint.test_rounding_twice_changes_the_midpoint_result) ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.001s

OK

test_empty_write_keeps_an_existing_range (__main__.KeepAhead.test_empty_write_keeps_an_existing_range) ... ok
test_matches_byte_sets_across_a_page_boundary (__main__.KeepAhead.test_matches_byte_sets_across_a_page_boundary) ... ok
test_same_page_does_not_mean_same_bytes (__main__.KeepAhead.test_same_page_does_not_mean_same_bytes) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.017s

OK
```

## Retrieved file SHA-256 hashes

```text
167F3A8EE9ECFF70AB015B225BBB4C4A7F4CDCB6266EC1127639FA4094FE29D6 any\PrototypeScarlett\emu\shader_cache.py
A3896DFFE78B0162FCCA82A4215167D33C5ACD1AB1DF0C31080F1018A873B8AB any\tests\test_shader_cache.py
202F92BE12E0CCCE1FCE47DB1D066C382B720056BD288DBF184C9EAAF3977551 continued\scripts\run_semantic_tests.py
FFE26E6DC19B71C4F7C413900734E3A688C2745C0C712BAA6C0ED863E7CDB42A continued\tests\test_run_semantic_tests.py
1EA9802CC83514DD78BE3D9BEBED7814DC56CFB4ACD65F74C40FB2DD39D9CEE2 klbf\tools\fps-session.py
637E973E86DE19045D56CF51A8B1BC377F8172D326D280EF26C19C1E130648BE klbf\tools\test_fps_session.py
```
