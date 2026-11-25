; Source-built quad/triangle for two wave64s. s17 points to a descriptor table.
; Its entry at byte 0x20 names the geometry buffer.
; Geometry dword 0 is (primitives << 12) | vertices. Dword 1 packs the second triangle's indices.
.text
s_mov_b32 s10, s17
s_mov_b32 s11, 0
s_load_dwordx4 s[24:27], s[10:11], 0x20
s_waitcnt lgkmcnt(0)
s_buffer_load_dword s15, s[24:27], null
s_buffer_load_dword s14, s[24:27], 4
s_waitcnt lgkmcnt(0)
s_mov_b32 s15, 0x2004
s_mov_b32 s26, 0x300402
s_cmp_eq_u32 s14, 1
s_cbranch_scc0 next_1
s_mov_b32 s26, 0x402
s_branch ready
next_1:
s_cmp_eq_u32 s14, 2
s_cbranch_scc0 next_2
s_mov_b32 s26, 0x300402
s_branch ready
next_2:
s_cmp_eq_u32 s14, 3
s_cbranch_scc0 next_3
s_mov_b32 s26, 0x402
s_branch ready
next_3:
s_cmp_eq_u32 s14, 4
s_cbranch_scc0 next_4
s_mov_b32 s26, 0x300402
s_branch ready
next_4:
s_cmp_eq_u32 s14, 5
s_cbranch_scc0 next_5
s_mov_b32 s26, 0x402
s_branch ready
next_5:
s_cmp_eq_u32 s14, 6
s_cbranch_scc0 next_6
s_mov_b32 s26, 0x300402
s_branch ready
next_6:
s_cmp_eq_u32 s14, 7
s_cbranch_scc0 next_7
s_mov_b32 s26, 0x402
s_branch ready
next_7:
s_cmp_eq_u32 s14, 8
s_cbranch_scc0 next_8
s_mov_b32 s26, 0x300402
s_branch ready
next_8:
s_cmp_eq_u32 s14, 9
s_cbranch_scc0 next_9
s_mov_b32 s26, 0x402
s_branch ready
next_9:
s_cmp_eq_u32 s14, 10
s_cbranch_scc0 next_10
s_mov_b32 s26, 0x300402
s_branch ready
next_10:
s_cmp_eq_u32 s14, 11
s_cbranch_scc0 next_11
s_mov_b32 s26, 0x402
s_branch ready
next_11:
s_cmp_eq_u32 s14, 12
s_cbranch_scc0 next_12
s_mov_b32 s26, 0x300402
s_branch ready
next_12:
s_cmp_eq_u32 s14, 13
s_cbranch_scc0 next_13
s_mov_b32 s26, 0x402
s_branch ready
next_13:
s_cmp_eq_u32 s14, 14
s_cbranch_scc0 next_14
s_mov_b32 s26, 0x300402
s_branch ready
next_14:
s_cmp_eq_u32 s14, 15
s_cbranch_scc0 next_15
s_mov_b32 s26, 0x402
s_branch ready
next_15:
s_cmp_eq_u32 s14, 16
s_cbranch_scc0 next_16
s_mov_b32 s26, 0x300402
s_branch ready
next_16:
s_cmp_eq_u32 s14, 17
s_cbranch_scc0 next_17
s_mov_b32 s26, 0x402
s_branch ready
next_17:
s_cmp_eq_u32 s14, 18
s_cbranch_scc0 next_18
s_mov_b32 s26, 0x300402
s_branch ready
next_18:
s_cmp_eq_u32 s14, 19
s_cbranch_scc0 next_19
s_mov_b32 s26, 0x402
s_branch ready
next_19:
s_cmp_eq_u32 s14, 20
s_cbranch_scc0 next_20
s_mov_b32 s26, 0x300402
s_branch ready
next_20:
s_cmp_eq_u32 s14, 21
s_cbranch_scc0 next_21
s_mov_b32 s26, 0x402
s_branch ready
next_21:
s_cmp_eq_u32 s14, 22
s_cbranch_scc0 next_22
s_mov_b32 s26, 0x300402
s_branch ready
next_22:
s_cmp_eq_u32 s14, 23
s_cbranch_scc0 next_23
s_mov_b32 s26, 0x402
s_branch ready
next_23:
s_cmp_eq_u32 s14, 24
s_cbranch_scc0 next_24
s_mov_b32 s26, 0x300402
s_branch ready
next_24:
s_cmp_eq_u32 s14, 25
s_cbranch_scc0 next_25
s_mov_b32 s26, 0x402
s_branch ready
next_25:
s_cmp_eq_u32 s14, 26
s_cbranch_scc0 next_26
s_mov_b32 s26, 0x300402
s_branch ready
next_26:
s_cmp_eq_u32 s14, 27
s_cbranch_scc0 next_27
s_mov_b32 s26, 0x402
s_branch ready
next_27:
s_cmp_eq_u32 s14, 28
s_cbranch_scc0 next_28
s_mov_b32 s26, 0x300402
s_branch ready
next_28:
s_cmp_eq_u32 s14, 29
s_cbranch_scc0 next_29
s_mov_b32 s26, 0x402
s_branch ready
next_29:
s_cmp_eq_u32 s14, 30
s_cbranch_scc0 next_30
s_mov_b32 s26, 0x300402
s_branch ready
next_30:
s_cmp_eq_u32 s14, 31
s_cbranch_scc0 next_31
s_mov_b32 s26, 0x402
s_branch ready
next_31:
ready:
s_mov_b32 s14, s26
s_bfe_u32 s16, s15, 0xc0000
s_lshr_b32 s19, s15, 12
v_mbcnt_lo_u32_b32 v0, -1, 0
v_mbcnt_hi_u32_b32 v0, -1, v0
s_bfe_u32 s8, s3, 0x40018
v_lshl_add_u32 v0, s8, 6, v0
s_mov_b64 s[22:23], exec
v_cmpx_eq_u32_e32 0, v0
s_cbranch_execz finish_alloc
s_mov_b32 m0, s15
s_sendmsg sendmsg(MSG_GS_ALLOC_REQ)
finish_alloc:
s_mov_b64 exec, s[22:23]
s_barrier
v_cmpx_gt_u32_e32 s16, v0
v_and_b32_e32 v10, 1, v0
v_and_b32_e32 v11, 2, v0
v_cmp_eq_u32_e64 s[20:21], 1, v10
v_cmp_eq_u32_e64 s[12:13], 2, v11
v_cndmask_b32_e64 v1, -1.0, 1.0, s[20:21]
v_cndmask_b32_e64 v2, -1.0, 1.0, s[12:13]
v_cndmask_b32_e64 v5, 0, 1.0, s[20:21]
v_cndmask_b32_e64 v6, 0, 1.0, s[12:13]
v_mov_b32_e32 v3, 0
v_mov_b32_e32 v4, 1.0
v_mov_b32_e32 v7, 0.5
exp pos0 v1, v2, v3, v4 done
exp param0 v5, v6, v7, v4
s_mov_b64 exec, s[22:23]
v_cmpx_gt_u32_e32 s19, v0
v_cmp_eq_u32_e64 s[20:21], 1, v0
v_mov_b32_e32 v9, 0x200400
v_cndmask_b32_e64 v9, v9, s14, s[20:21]
exp prim v9, off, off, off done
s_endpgm
