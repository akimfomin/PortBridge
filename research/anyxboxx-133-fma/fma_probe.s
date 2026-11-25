// SPDX-License-Identifier: GPL-3.0-or-later
// gfx1036 Wave32. Insert in a test kernel and read back v4:v7 instead of ending
// the program here. No memory operations depend on the test values.
.text
v_mov_b32_e32 v1, 0x3fc00000
v_mov_b32_e32 v2, 0x3f800001
v_mov_b32_e32 v3, 0x99800000
v_mov_b32_e32 v4, v3
v_mov_b32_e32 v5, v3
v_mov_b32_e32 v6, 0
v_mov_b32_e32 v7, 0
v_fmac_f32_e32 v4, v1, v2
v_fmac_legacy_f32_e32 v5, v1, v2
v_fmac_f32_e32 v6, v1, v2
v_fmac_legacy_f32_e32 v7, v1, v2
s_endpgm
