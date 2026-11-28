.amdgcn_target "amdgcn-amd-amdhsa--gfx1030"
.text
.globl inline16_probe
.p2align 8
.type inline16_probe,@function
inline16_probe:
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)
    s_mov_b32 s12, exec_lo

    // Three lanes, one candidate low half per lane, junk 0xabcd in every high half:
    // lane 0 = the f16 value, lane 1 = the low half of the f32 value, lane 2 = its high half.
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)
    v_mov_b32_e32 v10, 0xabcd3800        // 0.5:     f16 0x3800
    v_mov_b32_e32 v11, 0xabcdc400        // -4.0:    f16 0xc400
    v_mov_b32_e32 v12, 0xabcd3118        // 1/(2pi): f16 0x3118
    v_mov_b32_e32 v13, 0xabcd0001        // integer 1 (control)
    s_mov_b32 exec_lo, 2
    s_waitcnt_depctr depctr_sa_sdst(0)
    v_mov_b32_e32 v10, 0xabcd0000        // 0.5:     f32 0x3f000000, low half
    v_mov_b32_e32 v11, 0xabcd0000        // -4.0:    f32 0xc0800000, low half
    v_mov_b32_e32 v12, 0xabcdf983        // 1/(2pi): f32 0x3e22f983, low half
    v_mov_b32_e32 v13, 0xabcd0000
    s_mov_b32 exec_lo, 4
    s_waitcnt_depctr depctr_sa_sdst(0)
    v_mov_b32_e32 v10, 0xabcd3f00        // 0.5:     f32 high half
    v_mov_b32_e32 v11, 0xabcdc080        // -4.0:    f32 high half
    v_mov_b32_e32 v12, 0xabcd3e22        // 1/(2pi): f32 high half
    v_mov_b32_e32 v13, 0xabcd0001
    s_mov_b32 exec_lo, 7
    s_waitcnt_depctr depctr_sa_sdst(0)
    s_nop 1

    // VOPC: mask in VCC, inactive lanes 3-31 written as 0.
    v_cmp_eq_u16_e32 vcc_lo, 0.5, v10
    s_nop 4
    s_mov_b32 s20, vcc_lo
    v_cmp_eq_u16_e32 vcc_lo, -4.0, v11
    s_nop 4
    s_mov_b32 s21, vcc_lo
    v_cmp_eq_u16_e32 vcc_lo, 0.15915494, v12
    s_nop 4
    s_mov_b32 s22, vcc_lo
    v_cmp_eq_u16_e32 vcc_lo, 1, v13      // control: lanes 0 and 2
    s_nop 4
    s_mov_b32 s23, vcc_lo
    // VOP3: mask in an SGPR.
    v_cmp_eq_u16_e64 s24, 0.5, v10
    v_cmp_eq_u16_e64 s25, -4.0, v11
    v_cmp_eq_u16_e64 s26, 0.15915494, v12
    s_nop 4

    // SALU packs. s3 = 0x56781234: low half 0x1234, high half 0x5678.
    s_mov_b32 s3, 0x56781234
    s_pack_ll_b32_b16 s30, 0.5, s3               // {s3[15:0], c[15:0]}
    s_pack_ll_b32_b16 s31, s3, 0.15915494        // {c[15:0], s3[15:0]}
    s_pack_lh_b32_b16 s32, 0.15915494, s3        // {s3[31:16], c[15:0]}
    s_pack_hh_b32_b16 s33, 0.15915494, s3        // {s3[31:16], c[31:16]}
    s_pack_lh_b32_b16 s34, s3, 0.15915494        // {c[31:16], s3[15:0]}

    // Only lane 0 writes the result, before restoring the initial EXEC.
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)
    v_mov_b32_e32 v0, s12
    v_mov_b32_e32 v1, s20
    v_mov_b32_e32 v2, s21
    v_mov_b32_e32 v3, s22
    v_mov_b32_e32 v4, s23
    v_mov_b32_e32 v5, s24
    v_mov_b32_e32 v6, s25
    v_mov_b32_e32 v7, s26
    v_mov_b32_e32 v8, s30
    v_mov_b32_e32 v9, s31
    v_mov_b32_e32 v14, s32
    v_mov_b32_e32 v15, s33
    v_mov_b32_e32 v16, s34
    v_mov_b32_e32 v17, 0
    v_mov_b32_e32 v20, 0
    global_store_dwordx4 v20, v[0:3], s[4:5]
    global_store_dwordx4 v20, v[4:7], s[4:5] offset:16
    global_store_dwordx2 v20, v[8:9], s[4:5] offset:32
    global_store_dwordx4 v20, v[14:17], s[4:5] offset:40
    s_waitcnt_vscnt null, 0
    s_mov_b32 exec_lo, s12
    s_endpgm
.Linline16_probe_end:
.size inline16_probe, .Linline16_probe_end-inline16_probe

.section .rodata
.p2align 6
.amdhsa_kernel inline16_probe
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 21
    .amdhsa_next_free_sgpr 35
    .amdhsa_group_segment_fixed_size 0
    .amdhsa_private_segment_fixed_size 0
    .amdhsa_kernarg_size 8
    .amdhsa_wavefront_size32 1
    .amdhsa_float_round_mode_32 0
    .amdhsa_float_round_mode_16_64 0
    .amdhsa_float_denorm_mode_32 3
    .amdhsa_float_denorm_mode_16_64 3
    .amdhsa_dx10_clamp 1
    .amdhsa_ieee_mode 1
.end_amdhsa_kernel

.amdgpu_metadata
---
amdhsa.version: [ 1, 2 ]
amdhsa.target: amdgcn-amd-amdhsa--gfx1030
amdhsa.kernels:
  - .name: inline16_probe
    .symbol: inline16_probe.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 35
    .vgpr_count: 21
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
