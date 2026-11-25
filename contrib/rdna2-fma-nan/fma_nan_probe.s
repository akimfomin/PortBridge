.amdgcn_target "amdgcn-amd-amdhsa--gfx1030"

// Fourteen v_fma_f32 cases on one lane. The same body runs in two kernels that differ only
// in MODE.IEEE (.amdhsa_ieee_mode below). Output: EXEC, then f1-f14, as 15 dwords.
.macro fma_nan_body
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)

    s_mov_b32 s12, exec_lo
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)

    // Operands that are not inline constants. Each NaN has its own payload.
    v_mov_b32_e32 v20, 0x40400000    // 3.0
    v_mov_b32_e32 v21, 0x7fc00001    // quiet NaN 1
    v_mov_b32_e32 v22, 0x7fc00002    // quiet NaN 2
    v_mov_b32_e32 v23, 0x7fc00003    // quiet NaN 3
    v_mov_b32_e32 v24, 0x7f800005    // signalling NaN 5
    v_mov_b32_e32 v25, 0xffc00006    // negative quiet NaN 6
    v_mov_b32_e32 v26, 0x7fc00007    // quiet NaN 7
    v_mov_b32_e32 v27, 0x7fc00008    // quiet NaN 8
    v_mov_b32_e32 v28, 0x7fc00009    // quiet NaN 9
    v_mov_b32_e32 v29, 0x7fc0000a    // quiet NaN a
    v_mov_b32_e32 v30, 0x7fc0000b    // quiet NaN b
    v_mov_b32_e32 v31, 0x7fc0000c    // quiet NaN c
    v_mov_b32_e32 v32, 0x7f800000    // +inf
    v_mov_b32_e32 v33, 0xff800000    // -inf
    v_mov_b32_e32 v34, 0x7fc0000d    // quiet NaN d
    v_mov_b32_e32 v35, 0x7fc0000e    // quiet NaN e
    v_mov_b32_e32 v36, 0x7f80000f    // signalling NaN f
    s_nop 1

    //                D    S0   S1   S2
    v_fma_f32 v1,  2.0, v20, 1.0     // f1:  2 * 3 + 1 = 7 (control)
    v_fma_f32 v2,  v21, 1.0, 0       // f2:  NaN in S0
    v_fma_f32 v3,  1.0, v22, 0       // f3:  NaN in S1
    v_fma_f32 v4,  1.0, 1.0, v23     // f4:  NaN in S2
    v_fma_f32 v5,  v24, 1.0, 0       // f5:  signalling NaN in S0
    v_fma_f32 v6,  v25, 1.0, 0       // f6:  negative NaN in S0
    v_fma_f32 v7,  v26, 1.0, v27     // f7:  NaN in S0 and S2
    v_fma_f32 v8,  1.0, v28, v29     // f8:  NaN in S1 and S2
    v_fma_f32 v9,  v30, v31, 0       // f9:  NaN in S0 and S1
    v_fma_f32 v10, v32, 0, 1.0       // f10: +inf * 0 + 1
    v_fma_f32 v11, v32, 1.0, v33     // f11: +inf * 1 + -inf
    v_fma_f32 v12, v32, 0, v34       // f12: +inf * 0 + NaN
    v_fma_f32 v13, v35, v36, 0       // f13: quiet NaN in S0, signalling NaN in S1
    v_fma_f32 v14, v33, 0, 1.0       // f14: -inf * 0 + 1

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
.endm

.text
.globl fma_nan_ieee1
.p2align 8
.type fma_nan_ieee1,@function
fma_nan_ieee1:
    fma_nan_body
.Lfma_nan_ieee1_end:
.size fma_nan_ieee1, .Lfma_nan_ieee1_end-fma_nan_ieee1

.globl fma_nan_ieee0
.p2align 8
.type fma_nan_ieee0,@function
fma_nan_ieee0:
    fma_nan_body
.Lfma_nan_ieee0_end:
.size fma_nan_ieee0, .Lfma_nan_ieee0_end-fma_nan_ieee0

.section .rodata
.p2align 6
.amdhsa_kernel fma_nan_ieee1
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 37
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

.p2align 6
.amdhsa_kernel fma_nan_ieee0
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 37
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
    .amdhsa_ieee_mode 0
.end_amdhsa_kernel

.amdgpu_metadata
---
amdhsa.version: [ 1, 2 ]
amdhsa.target: amdgcn-amd-amdhsa--gfx1030
amdhsa.kernels:
  - .name: fma_nan_ieee1
    .symbol: fma_nan_ieee1.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 37
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
  - .name: fma_nan_ieee0
    .symbol: fma_nan_ieee0.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 37
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
