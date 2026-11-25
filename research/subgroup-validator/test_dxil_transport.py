# SPDX-License-Identifier: MIT
"""Independent local def-use controls for the narrow DXIL recognizer."""

import unittest

from dxil_transport import inspect_dxil


def listing(physical):
    lane = (
        "  %lane = call i32 @dx.op.flattenedThreadIdInGroup.i32(i32 96)\n"
        if physical == 64 else
        "  %origin = call i32 @dx.op.waveReadLaneFirst.i32(i32 118, i32 %offset)\n"
        "  %local = call i32 @dx.op.waveGetLaneIndex(i32 111)\n"
        "  %lane = add i32 %origin, %local\n"
    )
    selector = "%logical" if physical == 64 else "%host"
    return f"""
define void @main() {{
{lane}
  %bound_in = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind {{ i32 0, i32 0, i32 0, i8 1 }}, i32 0, i1 false)
  %in = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %bound_in, %dx.types.ResourceProperties {{ i32 4107, i32 0 }})
  %bound_out = call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind {{ i32 1, i32 1, i32 0, i8 1 }}, i32 1, i1 false)
  %out = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %bound_out, %dx.types.ResourceProperties {{ i32 4107, i32 0 }})
  %scaled = mul i32 %lane, 1024
  %base = add i32 %scaled, 512
  %address_slot = add i32 %base, 4
  %old_slot = add i32 %base, 8
  %wrong_slot = add i32 %base, 12
  %raw_data = call %dx.types.ResRet.i32 @dx.op.rawBufferLoad.i32(i32 139, %dx.types.Handle %in, i32 %base, i32 undef, i8 1, i32 4)
  %data = extractvalue %dx.types.ResRet.i32 %raw_data, 0
  %raw_a = call %dx.types.ResRet.i32 @dx.op.rawBufferLoad.i32(i32 139, %dx.types.Handle %in, i32 %address_slot, i32 undef, i8 1, i32 4)
  %addr = extractvalue %dx.types.ResRet.i32 %raw_a, 0
  %raw_old = call %dx.types.ResRet.i32 @dx.op.rawBufferLoad.i32(i32 139, %dx.types.Handle %in, i32 %old_slot, i32 undef, i8 1, i32 4)
  %old = extractvalue %dx.types.ResRet.i32 %raw_old, 0
  %shifted = lshr i32 %addr, 2
  %index = and i32 %shifted, 31
  %half = and i32 %lane, 32
  %logical = or i32 %half, %index
  %host = and i32 %logical, 31
  %read = call i32 @dx.op.waveReadLaneAt.i32(i32 117, i32 %data, i32 {selector})
  %src_high = icmp uge i32 %logical, 32
  %src_exec = select i1 %src_high, i32 -1431655766, i32 1431655765
  %src_shift = lshr i32 %src_exec, %host
  %src_bit = and i32 %src_shift, 1
  %src_on = icmp ne i32 %src_bit, 0
  %masked = select i1 %src_on, i32 %read, i32 0
  %dst_high = icmp uge i32 %lane, 32
  %dst_exec = select i1 %dst_high, i32 -1431655766, i32 1431655765
  %dst_index = and i32 %lane, 31
  %dst_shift = lshr i32 %dst_exec, %dst_index
  %dst_bit = and i32 %dst_shift, 1
  %dst_on = icmp ne i32 %dst_bit, 0
  %final = select i1 %dst_on, i32 %masked, i32 %old
  call void @dx.op.rawBufferStore.i32(i32 140, %dx.types.Handle %out, i32 %old_slot, i32 undef, i32 %final, i32 undef, i32 undef, i32 undef, i8 1, i32 4)
  ret void
}}
"""


class DirectDxilTransportTest(unittest.TestCase):
    def test_positive_modalities_and_participation_gate(self):
        for physical in (32, 64):
            with self.subTest(physical=physical):
                row, = inspect_dxil(listing(physical), physical)
                self.assertEqual("recognized", row["status"])
                self.assertEqual("passes modeled domain", row["checks"]["superset"]["status"])
                self.assertEqual("refuted", row["checks"]["independent"]["status"])
                self.assertEqual((1, 0, 2), tuple(row[field] for field in ("address_vgpr", "data_vgpr", "destination_vgpr")))

    def test_native_wrong_source_half_is_refuted(self):
        bad = listing(64).replace("%half = and i32 %lane, 32", "%half = and i32 %lane, 0")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("refuted", row["checks"]["superset"]["status"])

    def test_split_must_read_logical_exec_bank(self):
        bad = listing(32).replace("%src_high = icmp uge i32 %logical, 32",
                                  "%src_high = icmp uge i32 %host, 32")
        row, = inspect_dxil(bad, 32)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("different lanes", row["reason"])

    def test_source_and_destination_must_share_exec_snapshot(self):
        bad = listing(32).replace("%dst_high, i32 -1431655766", "%dst_high, i32 0")
        row, = inspect_dxil(bad, 32)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("different guest EXEC snapshots", row["reason"])

    def test_inactive_destination_must_match_output_slot(self):
        bad = listing(64).replace("Handle %out, i32 %old_slot", "Handle %out, i32 %wrong_slot")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("different test-register addresses", row["reason"])

    def test_inactive_destination_must_use_output_resource(self):
        bad = listing(64).replace("Handle %out, i32 %old_slot", "Handle %in, i32 %old_slot")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("test output UAV at u1", row["reason"])

    def test_next_lane_register_address_is_rejected(self):
        bad = listing(64).replace("%old_slot = add i32 %base, 8", "%old_slot = add i32 %base, 1024")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("exceeds its lane allocation", row["reason"])

    def test_duplicate_write_to_a_register_at_equivalent_address(self):
        original = listing(64)
        store = next(line for line in original.splitlines() if "@dx.op.rawBufferStore" in line)
        other = store.replace("%old_slot", "%alias_slot").replace("%final", "3")
        bad = original.replace("  ret void", "  %alias_slot = add i32 %base, 8\n" + other + "\n  ret void")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("repeated output register write", row["reason"])

    def test_literal_store_must_stay_in_the_scalar_prefix(self):
        original = listing(64)
        store = next(line for line in original.splitlines() if "@dx.op.rawBufferStore" in line)
        other = store.replace("%old_slot", "520").replace("%final", "3")
        bad = original.replace("  ret void", other + "\n  ret void")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("literal store outside the scalar prefix", row["reason"])

    def test_path_that_bypasses_the_output_is_rejected(self):
        bad = listing(64).replace(
            "  call void @dx.op.rawBufferStore",
            "  br i1 %src_on, label %7, label %8\n; <label>:7\n  call void @dx.op.rawBufferStore",
        ).replace("  ret void", "  ret void\n; <label>:8\n  ret void")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("path does not reach", row["reason"])

    def test_an_assigned_atomic_write_is_unmodeled_on_the_output_path(self):
        bad = listing(64).replace("  ret void", "  %previous = atomicrmw add i32* %x, i32 1 seq_cst\n  ret void")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("unsupported output store", row["reason"])

    def test_consistently_swapped_exec_words_are_rejected(self):
        bad = listing(64).replace("-1431655766, i32 1431655765", "1431655765, i32 -1431655766")
        row, = inspect_dxil(bad, 64)
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("unexpected literal guest EXEC pair", row["reason"])


if __name__ == "__main__":
    unittest.main()
