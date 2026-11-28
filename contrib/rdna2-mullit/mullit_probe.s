.amdgcn_target "amdgcn-amd-amdhsa--gfx1030"
.text
.globl mullit_probe
.p2align 8
.type mullit_probe,@function
mullit_probe:
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)

    s_mov_b32 s12, exec_lo
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)

    // Operands that are not inline constants.
    v_mov_b32_e32 v20, 0x40400000    // 3.0
    v_mov_b32_e32 v21, 0x7fc00000    // quiet NaN
    v_mov_b32_e32 v22, 0x7f800000    // +inf
    v_mov_b32_e32 v23, 0xff800000    // -inf
    v_mov_b32_e32 v24, 0xff7fffff    // -MAX_FLOAT
    v_mov_b32_e32 v25, 0x7f7fffff    // +MAX_FLOAT
    v_mov_b32_e32 v26, 0x80000000    // -0.0
    v_mov_b32_e32 v27, 0x40a00000    // 5.0
    s_nop 1

    //                   D    S0   S1   S2
    v_mullit_f32 v1,  2.0, v20, 1.0     // c1:  2 * 3, S2 = 1
    v_mullit_f32 v2,  2.0, v20, 0       // c2:  2 * 3, S2 = +0
    v_mullit_f32 v3,  2.0, v20, -1.0    // c3:  2 * 3, S2 = -1
    v_mullit_f32 v4,  2.0, v20, v21     // c4:  2 * 3, S2 = NaN
    v_mullit_f32 v5,  0, v22, 1.0       // c5:  0 * +inf
    v_mullit_f32 v6,  v22, 0, 1.0       // c6:  +inf * 0
    v_mullit_f32 v7,  2.0, v23, 1.0     // c7:  2 * -inf
    v_mullit_f32 v8,  2.0, v21, 1.0     // c8:  2 * NaN
    v_mullit_f32 v9,  2.0, v24, 1.0     // c9:  2 * -MAX
    v_mullit_f32 v10, v26, v27, 1.0     // c10: -0 * 5
    v_mullit_f32 v11, v25, 2.0, 1.0     // c11: MAX * 2
    v_mullit_f32 v12, v21, 0, 1.0       // c12: NaN * 0
    v_mullit_f32 v13, 2.0, v20, v26     // c13: 2 * 3, S2 = -0
    v_mullit_f32 v14, 0, v21, 1.0       // c14: 0 * NaN

    // Only lane 0 writes the result, before restoring the initial EXEC.
    v_mov_b32_e32 v0, s12
    v_mov_b32_e32 v15, 0
    global_store_dwordx4 v15, v[0:3], s[4:5]
    global_store_dwordx4 v15, v[4:7], s[4:5] offset:16
    global_store_dwordx4 v15, v[8:11], s[4:5] offset:32
    global_store_dwordx3 v15, v[12:14], s[4:5] offset:48
    s_waitcnt_vscnt null, 0
    s_mov_b32 exec_lo, s12
    s_endpgm
.Lmullit_probe_end:
.size mullit_probe, .Lmullit_probe_end-mullit_probe

.section .rodata
.p2align 6
.amdhsa_kernel mullit_probe
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 28
    .amdhsa_next_free_sgpr 13
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
  - .name: mullit_probe
    .symbol: mullit_probe.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 28
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
