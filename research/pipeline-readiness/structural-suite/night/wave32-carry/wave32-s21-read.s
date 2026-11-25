s_and_b32 s6, exec_lo, 0xaaaaaaaa
s_bcnt1_i32_b32 s7, s6
v_mbcnt_lo_u32_b32 v2, -1, 0
v_and_b32_e32 v2, 1, v2
v_add_co_u32 v3, s21, -1, v2
v_add_co_u32 v3, s20, 0, v2
v_bcnt_u32_b32_e64 v4, s21, 0
v_cvt_f32_u32_e32 v4, v4
v_cvt_f32_u32_e32 v5, s7
v_mov_b32_e32 v6, 1.0
exp mrt0 v4, v5, v6, v6 done vm
s_endpgm
