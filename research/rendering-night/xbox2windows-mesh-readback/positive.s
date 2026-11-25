s_mov_b32 s10, s17
s_mov_b32 s11, 0
s_load_dwordx4 s[24:27], s[10:11], 0x20
s_load_dwordx4 s[16:19], s[10:11], 0x60
s_load_dwordx4 s[20:23], s[10:11], 0x80
s_waitcnt lgkmcnt(0)
s_buffer_load_dword s15, s[24:27], null
s_buffer_load_dword s30, s[16:19], 0x4
s_buffer_load_dword s31, s[20:23], 0xc
s_waitcnt lgkmcnt(0)
v_mbcnt_lo_u32_b32 v0, -1, 0
v_mbcnt_hi_u32_b32 v0, -1, v0
s_bfe_u32 s8, s3, 0x40018
v_lshl_add_u32 v0, s8, 6, v0
s_mov_b64 s[22:23], exec
v_mbcnt_lo_u32_b32 v7, -1, 0
v_mbcnt_hi_u32_b32 v7, -1, v7
v_mov_b32_e32 v30, 0
s_mov_b32 s40, 1
s_mov_b32 s41, 0x100
s_mov_b64 exec, s[40:41]
s_mov_b64 s[40:41], exec
s_mov_b64 exec, 1
s_mov_b32 s44, 8
s_mov_b32 s45, 40
s_mov_b32 s47, 0
v_writelane_b32 v30, s40, 8
v_writelane_b32 v30, s41, 40
s_mov_b32 s40, 0
s_mov_b32 s41, 0
v_readlane_b32 s40, v30, 8
v_readlane_b32 s41, v30, 40
s_cmp_eq_u32 s40, 1
s_cbranch_scc0 1
s_mov_b64 exec, s[40:41]
v_cmpx_eq_u32_e32 40, v7
s_mov_b32 s46, -0.5
s_cbranch_execz 1
s_mov_b32 s46, 0.5
s_mov_b64 exec, s[22:23]
v_cmpx_eq_u32_e32 0, v0
s_cbranch_execz 2
s_mov_b32 s7, s15
s_mov_b32 m0, s7
s_cbranch_execz 1
s_sendmsg sendmsg(MSG_GS_ALLOC_REQ)
v_mov_b32_e32 v9, 0x200400
exp prim v9, off, off, off done
s_mov_b64 exec, s[22:23]
v_cmpx_gt_u32_e32 3, v0
v_cmp_eq_u32_e64 s[10:11], 1, v0
v_cmp_eq_u32_e64 s[12:13], 2, v0
v_mov_b32_e32 v8, 0x40400000
v_mov_b32_e32 v9, 0xbf800000
v_cndmask_b32_e64 v1, v9, v8, s[10:11]
v_cndmask_b32_e64 v2, v9, v8, s[12:13]
v_mov_b32_e32 v3, s46
v_mov_b32_e32 v4, 0x3f800000
exp pos0 v1, v2, v3, v4 done
s_endpgm
