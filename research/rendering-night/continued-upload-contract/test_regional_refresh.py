# SPDX-License-Identifier: MIT
"""Deterministic byte oracle and failure-phase controls for fixed sampled images."""

from dataclasses import replace
import importlib.util
import itertools
from pathlib import Path
import sys
import unittest


spec = importlib.util.spec_from_file_location("regional_refresh", Path(__file__).with_name("regional_refresh.py"))
proof = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = proof
spec.loader.exec_module(proof)
from regional_refresh import (Authority, Identity, Outcome, Refresh, RegionalRefresh, Snapshot,
                              Submission, Texture, TrackedLayout, UploadMode)


class MemoryBackend:
    """Physical tile bytes and progress separate from the coordinator's committed shadow."""

    def __init__(self, tile_bytes):
        self.tile_bytes = tile_bytes
        self.images = {}
        self.queued = {}
        self.calls = []
        self.outcomes = []
        self.during = None

    def _copy(self, request):
        if request.mode is UploadMode.FULL:
            self.images[request.image] = request.source.data
            return
        target = bytearray(self.images[request.image])
        for tile in request.tiles:
            start = tile * self.tile_bytes
            end = start + self.tile_bytes
            target[start:end] = request.source.data[start:end]
        self.images[request.image] = bytes(target)

    def transfer(self, request):
        self.calls.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else Outcome(Submission.PUBLISHED)
        if outcome.status in (Submission.PUBLISHED, Submission.COMPLETE_WITHOUT_ACQUIRES):
            self._copy(request)
        if outcome.status is Submission.COMPLETION_UNKNOWN:
            self.queued[outcome.timeline] = request
        if self.during:
            self.during()
        return outcome

    def complete_primary(self, timeline):
        self._copy(self.queued.pop(timeline))


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.cache = RegionalRefresh(tile_bytes=4, tile_count=4, sparse_limit=2)
        self.tex = Texture(Identity(13, 101, 1))
        self.backend = MemoryBackend(tile_bytes=4)
        self.original = bytes(range(16))

    def data(self, changes):
        target = bytearray(self.original)
        for index, new_value in changes.items():
            target[index] = new_value
        return bytes(target)

    def upload(self, data, tracked=TrackedLayout.GENERAL):
        captured = Snapshot(data, self.tex.source_epoch) if data is not None else None
        return self.cache.refresh(self.tex, captured, tracked, self.backend.transfer)

    def warm(self):
        self.assertEqual(self.upload(self.original, TrackedLayout.UNDEFINED), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)
        self.assertFalse(self.tex.dirty)

    def test_first_image_then_exact_regions(self):
        self.warm()
        self.tex.note_write()
        new = self.data({1: 100, 15: 101})
        self.assertEqual(self.upload(new), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].tiles, (0, 3))
        self.assertEqual(self.backend.images[self.tex.image], new)
        self.assertEqual(self.cache.shadow, (self.tex.image, new))
        self.assertFalse(self.tex.dirty)

    def test_mixed_other_committed_images_and_single_entry_bound(self):
        self.warm()
        original = self.tex
        self.tex = Texture(Identity(14, 201, 1))
        self.assertEqual(self.upload(self.original), Refresh.PUBLISHED)
        self.assertEqual(self.cache.shadow[0], self.tex.image)
        self.tex = original
        self.tex.note_write()
        self.assertEqual(self.upload(self.data({0: 99})), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)

    def test_dense_zero_and_unsupported_whole_copy(self):
        self.warm()
        for changes in ({0: 17, 4: 18, 8: 19}, {}, {1: 34}):
            self.tex.note_write()
            if changes == {1: 34}:
                self.tex.layout = replace(self.tex.layout, mips=2)
            self.assertEqual(self.upload(self.data(changes)), Refresh.PUBLISHED)
            self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)
        self.assertIsNone(self.cache.shadow)

    def test_staging_declines_undefined_layout_before_recording(self):
        self.warm()
        self.tex.note_write()
        self.backend.outcomes = [Outcome(Submission.REFUSED_OLD_LAYOUT)]
        new = self.data({7: 53})
        self.assertEqual(self.upload(new), Refresh.PUBLISHED)
        self.assertEqual([c.mode for c in self.backend.calls], [UploadMode.FULL, UploadMode.REGION, UploadMode.FULL])
        self.assertEqual(self.backend.images[self.tex.image], new)

    def test_layout_already_unknown_does_not_try_partial(self):
        self.warm()
        self.tex.note_write()
        self.assertEqual(self.upload(self.data({2: 33}), TrackedLayout.OTHER), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)

    def test_backing_and_host_route_eligibility(self):
        self.warm()
        self.tex.note_write()
        self.tex.backed = False
        self.assertEqual(self.upload(self.original), Refresh.DEFER)
        self.assertEqual(len(self.backend.calls), 1)
        self.assertTrue(self.tex.dirty)
        self.assertIsNone(self.cache.shadow)
        self.tex.backed = True
        self.tex.staged = False
        self.assertEqual(self.upload(self.data({1: 29})), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)
        self.assertIsNone(self.cache.shadow)

    def test_ineligible_geometry_and_format_require_full(self):
        for variant in (dict(width=513), dict(height=384), dict(layers=2), dict(samples=2),
                        dict(planes=2), dict(format="BC1"), dict(tiling="LINEAR"), dict(in_mip_tail=True)):
            with self.subTest(variant=variant):
                self.cache = RegionalRefresh(tile_bytes=4, tile_count=4, sparse_limit=2)
                self.tex = Texture(Identity(13, 101, 1))
                self.backend = MemoryBackend(tile_bytes=4)
                self.warm()
                self.tex.rebind(replace(self.tex.image, generation=2))
                self.tex.layout = replace(self.tex.layout, **variant)
                self.assertEqual(self.upload(self.data({1: 67})), Refresh.PUBLISHED)
                self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)
                self.assertIsNone(self.cache.shadow)

    def test_new_owner_even_if_raw_handles_reused(self):
        self.warm()
        old = self.tex.image
        self.assertTrue(self.cache.retire(old))
        self.tex.rebind(replace(old, generation=2))
        self.assertEqual(self.upload(self.data({0: 91})), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)

    def test_gpu_authority_never_writes(self):
        self.warm()
        self.tex.authority = Authority.GPU
        self.tex.note_write()
        self.assertEqual(self.upload(self.data({8: 94})), Refresh.GPU_OWNED)
        self.assertEqual(len(self.backend.calls), 1)
        self.assertIsNone(self.cache.shadow)
        self.assertTrue(self.tex.dirty)
        self.tex.authority = Authority.EXISTING_CPU_PATH
        self.assertEqual(self.upload(self.data({8: 94})), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)
        self.assertIsNone(self.cache.shadow)

    def test_read_failure_and_older_snapshot_do_not_consume_dirty(self):
        self.warm()
        self.tex.note_write()
        self.assertEqual(self.upload(None), Refresh.DEFER)
        old = Snapshot(self.original, self.tex.applied_epoch)
        self.assertEqual(self.cache.refresh(self.tex, old, TrackedLayout.GENERAL, self.backend.transfer), Refresh.DEFER)
        self.assertEqual(len(self.backend.calls), 1)
        self.assertTrue(self.tex.dirty)
        self.assertEqual(self.cache.shadow, (self.tex.image, self.original))

    def test_before_submit_failure_keeps_previous_image(self):
        self.warm()
        self.tex.note_write()
        self.backend.outcomes = [Outcome(Submission.NOT_SUBMITTED)]
        new = self.data({4: 37})
        self.assertEqual(self.upload(new), Refresh.DEFER)
        self.assertTrue(self.tex.dirty)
        self.assertIsNone(self.cache.shadow)
        self.assertEqual(self.backend.images[self.tex.image], self.original)
        self.assertEqual(self.upload(new), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)

    def test_primary_completed_but_consumer_acquire_failed(self):
        self.warm()
        self.tex.note_write()
        new = self.data({4: 38})
        self.backend.outcomes = [Outcome(Submission.COMPLETE_WITHOUT_ACQUIRES)]
        self.assertEqual(self.upload(new), Refresh.DEFER)
        self.assertEqual(self.backend.images[self.tex.image], new)
        self.assertTrue(self.tex.dirty)
        self.assertIsNone(self.cache.shadow)
        self.assertFalse(self.cache.may_sample_image(self.tex.image))
        self.backend.outcomes = [Outcome(Submission.NOT_SUBMITTED)]
        self.assertEqual(self.upload(self.original), Refresh.DEFER)
        self.assertFalse(self.cache.may_sample_image(self.tex.image))
        self.assertEqual(self.upload(self.original), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)
        self.assertEqual(self.backend.images[self.tex.image], self.original)
        self.assertTrue(self.cache.may_sample_image(self.tex.image))

    def test_unknown_completion_quarantines_staging_and_old_image(self):
        self.warm()
        self.tex.note_write()
        old = self.tex.image
        first = self.data({1: 77})
        self.backend.outcomes = [Outcome(Submission.COMPLETION_UNKNOWN, timeline=7)]
        self.assertEqual(self.upload(first), Refresh.QUARANTINED)
        self.assertFalse(self.cache.may_release_image(old))
        self.assertFalse(self.cache.may_sample_image(old))
        self.assertFalse(self.cache.retire(old))
        self.tex.rebind(replace(old, generation=2))
        self.assertEqual(self.upload(self.original), Refresh.QUARANTINED)
        self.cache.confirm_primary(6)
        self.assertEqual(self.upload(self.original), Refresh.QUARANTINED)
        self.backend.complete_primary(7)
        self.cache.confirm_primary(7)
        self.assertTrue(self.cache.may_release_image(old))
        self.assertFalse(self.cache.may_sample_image(old))
        self.assertEqual(self.upload(self.original), Refresh.QUARANTINED)
        self.assertTrue(self.cache.retire(old))
        self.assertEqual(self.upload(self.original), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)
        self.assertEqual(self.backend.images[old], first)
        self.assertEqual(self.backend.images[self.tex.image], self.original)

    def test_device_loss_never_advances_dirty_epoch(self):
        self.warm()
        self.tex.note_write()
        self.backend.outcomes = [Outcome(Submission.DEVICE_LOST)]
        self.assertEqual(self.upload(self.data({3: 82})), Refresh.DEVICE_LOST)
        self.assertTrue(self.tex.dirty)
        self.assertFalse(self.cache.may_sample_image(self.tex.image))
        self.assertFalse(self.cache.may_release_image(self.tex.image))
        self.assertEqual(self.upload(self.original), Refresh.DEVICE_LOST)
        self.assertEqual(len(self.backend.calls), 2)

    def test_new_notifier_during_transfer_is_not_consumed(self):
        self.warm()
        self.tex.note_write()
        first, second = self.data({0: 19}), self.data({0: 19, 15: 45})
        self.backend.during = self.tex.note_write
        self.assertEqual(self.upload(first), Refresh.PUBLISHED)
        self.assertTrue(self.tex.dirty)
        self.assertEqual(self.tex.applied_epoch, self.tex.source_epoch - 1)
        self.assertEqual(self.cache.shadow, (self.tex.image, first))
        self.backend.during = None
        self.assertEqual(self.upload(second), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].tiles, (3,))
        self.assertFalse(self.tex.dirty)

    def test_generation_change_during_callback_keeps_new_entry_dirty(self):
        self.warm()
        self.tex.note_write()
        incoming = replace(self.tex.image, generation=2)
        self.backend.during = lambda: self.tex.rebind(incoming)
        self.assertEqual(self.upload(self.data({2: 63})), Refresh.DEFER)
        self.assertTrue(self.tex.dirty)
        self.assertIsNone(self.cache.shadow)
        self.assertNotIn(incoming, self.backend.images)
        self.backend.during = None
        self.assertEqual(self.upload(self.original), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)

    def test_all_256_previous_next_tile_masks(self):
        for previous, after in itertools.product(range(16), repeat=2):
            self.cache = RegionalRefresh(tile_bytes=4, tile_count=4, sparse_limit=2)
            self.tex = Texture(Identity(13, 101, 1))
            self.backend = MemoryBackend(tile_bytes=4)
            prev_bytes = bytes(byte for tile in range(4) for byte in [bool(previous & (1 << tile))] * 4)
            after_bytes = bytes(byte for tile in range(4) for byte in [bool(after & (1 << tile))] * 4)
            self.assertEqual(self.upload(prev_bytes), Refresh.PUBLISHED)
            self.tex.note_write()
            self.assertEqual(self.upload(after_bytes), Refresh.PUBLISHED)
            self.assertEqual(self.backend.images[self.tex.image], after_bytes)
            width = (previous ^ after).bit_count()
            if 0 < width <= 2:
                self.assertEqual(self.backend.calls[-1].mode, UploadMode.REGION)
                self.assertEqual(len(self.backend.calls[-1].tiles), width)
            else:
                self.assertEqual(self.backend.calls[-1].mode, UploadMode.FULL)

    def test_actual_shape_one_mebibyte_and_two_disjoint_tiles(self):
        self.cache = RegionalRefresh()
        self.backend = MemoryBackend(tile_bytes=65_536)
        start = bytes(range(256)) * 4096
        self.assertEqual(self.upload(start, TrackedLayout.UNDEFINED), Refresh.PUBLISHED)
        updated = bytearray(start)
        updated[6 * 65_536 + 13] ^= 0x5a
        updated[12 * 65_536 + 55] ^= 0x5a
        self.tex.note_write()
        self.assertEqual(self.upload(bytes(updated)), Refresh.PUBLISHED)
        self.assertEqual(self.backend.calls[-1].tiles, (6, 12))
        self.assertEqual(self.backend.images[self.tex.image], updated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
