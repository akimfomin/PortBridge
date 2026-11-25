# SPDX-License-Identifier: MIT
"""Local parser controls independently authored from the SPIR-V grammar."""

import unittest

from spirv_transport import UnsupportedPattern, inspect


MODULE = """
OpCapability Shader
OpCapability GroupNonUniform
OpCapability GroupNonUniformBallot
OpCapability GroupNonUniformShuffle
OpMemoryModel Logical GLSL450
OpEntryPoint GLCompute %main "main" %lane_input
OpExecutionMode %main LocalSize 64 1 1
OpDecorate %lane_input BuiltIn SubgroupLocalInvocationId
%void = OpTypeVoid
%bool = OpTypeBool
%word = OpTypeInt 32 0
%v4 = OpTypeVector %word 4
%function = OpTypeFunction %void
%input_word = OpTypePointer Input %word
%local_word = OpTypePointer Function %word
%zero = OpConstant %word 0
%shift = OpConstant %word 2
%scope = OpConstant %word 3
%low_mask = OpConstant %word 31
%high_mask = OpConstant %word 32
%all_bits = OpConstant %word 4294967295
%always = OpConstantTrue %bool
%lane_input = OpVariable %input_word Input
%main = OpFunction %void None %function
%entry = OpLabel
%slot = OpVariable %local_word Function %zero
%self = OpLoad %word %lane_input
%active = OpIEqual %bool %self %high_mask
%data = OpIAdd %word %self %shift
%address = OpIAdd %word %self %zero
%indexed = OpShiftRightLogical %word %address %shift
%index = OpBitwiseAnd %word %indexed %low_mask
%half = OpBitwiseAnd %word %self %high_mask
%desired = OpBitwiseOr %word %half %index
%input_value = OpSelect %word %active %data %zero
%ballot = OpGroupNonUniformBallot %v4 %scope %always
%present = OpGroupNonUniformBallotBitExtract %bool %scope %ballot %desired
%safe_index = OpSelect %word %present %desired %self
%read = OpGroupNonUniformShuffle %word %scope %input_value %safe_index
%present_mask = OpSelect %word %present %all_bits %zero
%read_bits = OpBitwiseAnd %word %read %present_mask
%exec_mask = OpSelect %word %active %all_bits %zero
%complement = OpNot %word %exec_mask
%old = OpLoad %word %slot
%new_bits = OpBitwiseAnd %word %read_bits %exec_mask
%old_bits = OpBitwiseAnd %word %old %complement
%merge = OpBitwiseOr %word %new_bits %old_bits
OpStore %slot %merge
OpReturn
OpFunctionEnd
"""


class SpirvTransportTest(unittest.TestCase):
    def test_recognized_and_participation_contract_checked(self):
        row, = inspect(MODULE)["shuffles"]
        self.assertEqual("recognized", row["status"])
        self.assertEqual({"address_input": "%self", "offset_bytes": 0, "data_input": "%data",
                          "guest_active": "%active", "old_value": "%old", "destination": "%slot"}, row["bindings"])
        self.assertEqual("passes modeled domain", row["checks"]["64/superset"]["status"])
        self.assertEqual("refuted", row["checks"]["64/independent"]["status"])

    def test_wrong_half_is_refuted_only_with_64_lane_host(self):
        mutated = MODULE.replace("OpBitwiseAnd %word %self %high_mask", "OpBitwiseAnd %word %self %zero")
        row, = inspect(mutated)["shuffles"]
        self.assertEqual("refuted", row["checks"]["64/superset"]["status"])
        self.assertEqual("passes modeled domain", row["checks"]["32/superset"]["status"])

    def test_fallback_to_wrong_lane_is_unmodeled(self):
        row, = inspect(MODULE.replace("%present %desired %self", "%present %desired %zero"))["shuffles"]
        self.assertEqual("unmodeled", row["status"])
        self.assertNotIn("checks", row)

    def test_wrong_execution_model_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedPattern, "one compute entry point"):
            inspect(MODULE.replace("GLCompute", "Fragment"))

    def test_intervening_store_is_unmodeled(self):
        changed = MODULE.replace("%new_bits =", "OpStore %slot %shift\n%new_bits =")
        row, = inspect(changed)["shuffles"]
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("old-register", row["reason"])

    def test_shuffle_outside_entry_is_unmodeled(self):
        changed = MODULE.replace('GLCompute %main "main"', 'GLCompute %other "main"')
        row, = inspect(changed)["shuffles"]
        self.assertEqual("unmodeled", row["status"])
        self.assertIn("outside the compute entry", row["reason"])


if __name__ == "__main__":
    unittest.main()
