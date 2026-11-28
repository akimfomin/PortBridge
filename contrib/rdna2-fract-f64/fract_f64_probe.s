.amdgcn_target "amdgcn-amd-amdhsa--gfx1030"

// Ten v_fract_f64 cases on one lane. The same body runs in two kernels that differ only
// in MODE.IEEE (.amdhsa_ieee_mode below). Output: EXEC, a zero dword, then d1-d10 as
// ten little-endian doubles (22 dwords).
.macro fract_f64_body
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)

    s_mov_b32 s12, exec_lo
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)

    // Inputs, low dword first.
    v_mov_b32_e32 v40, 0                 // d1:  1.25
    v_mov_b32_e32 v41, 0x3ff40000
    v_mov_b32_e32 v42, 0                 // d2:  -1.25
    v_mov_b32_e32 v43, 0xbff40000
    v_mov_b32_e32 v44, 0x0c924223        // d3:  -1e-20
    v_mov_b32_e32 v45, 0xbbc79ca1
    v_mov_b32_e32 v46, 0                 // d4:  -2^-53
    v_mov_b32_e32 v47, 0xbca00000
    v_mov_b32_e32 v48, 0                 // d5:  -0.0
    v_mov_b32_e32 v49, 0x80000000
    v_mov_b32_e32 v50, 0                 // d6:  +inf
    v_mov_b32_e32 v51, 0x7ff00000
    v_mov_b32_e32 v52, 0                 // d7:  -inf
    v_mov_b32_e32 v53, 0xfff00000
    v_mov_b32_e32 v54, 1                 // d8:  signalling NaN, payload 1
    v_mov_b32_e32 v55, 0x7ff00000
    v_mov_b32_e32 v56, 0x123             // d9:  negative quiet NaN, payload 0x123
    v_mov_b32_e32 v57, 0xfff80000
    v_mov_b32_e32 v58, 0x8800759c        // d10: 1e300
    v_mov_b32_e32 v59, 0x7e37e43c
    s_nop 1

    v_fract_f64_e32 v[2:3],   v[40:41]   // d1
    v_fract_f64_e32 v[4:5],   v[42:43]   // d2
    v_fract_f64_e32 v[6:7],   v[44:45]   // d3
    v_fract_f64_e32 v[8:9],   v[46:47]   // d4
    v_fract_f64_e32 v[10:11], v[48:49]   // d5
    v_fract_f64_e32 v[12:13], v[50:51]   // d6
    v_fract_f64_e32 v[14:15], v[52:53]   // d7
    v_fract_f64_e32 v[16:17], v[54:55]   // d8
    v_fract_f64_e32 v[18:19], v[56:57]   // d9
    v_fract_f64_e32 v[20:21], v[58:59]   // d10

    // Only lane 0 writes the result, before restoring the initial EXEC.
    v_mov_b32_e32 v0, s12
    v_mov_b32_e32 v1, 0
    v_mov_b32_e32 v60, 0
    global_store_dwordx4 v60, v[0:3], s[4:5]
    global_store_dwordx4 v60, v[4:7], s[4:5] offset:16
    global_store_dwordx4 v60, v[8:11], s[4:5] offset:32
    global_store_dwordx4 v60, v[12:15], s[4:5] offset:48
    global_store_dwordx4 v60, v[16:19], s[4:5] offset:64
    global_store_dwordx2 v60, v[20:21], s[4:5] offset:80
    s_waitcnt_vscnt null, 0
    s_mov_b32 exec_lo, s12
    s_endpgm
.endm

.text
.globl fract_f64_ieee1
.p2align 8
.type fract_f64_ieee1,@function
fract_f64_ieee1:
    fract_f64_body
.Lfract_f64_ieee1_end:
.size fract_f64_ieee1, .Lfract_f64_ieee1_end-fract_f64_ieee1

.globl fract_f64_ieee0
.p2align 8
.type fract_f64_ieee0,@function
fract_f64_ieee0:
    fract_f64_body
.Lfract_f64_ieee0_end:
.size fract_f64_ieee0, .Lfract_f64_ieee0_end-fract_f64_ieee0

.section .rodata
.p2align 6
.amdhsa_kernel fract_f64_ieee1
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 61
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
.amdhsa_kernel fract_f64_ieee0
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 61
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
  - .name: fract_f64_ieee1
    .symbol: fract_f64_ieee1.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 61
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
  - .name: fract_f64_ieee0
    .symbol: fract_f64_ieee0.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 61
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
