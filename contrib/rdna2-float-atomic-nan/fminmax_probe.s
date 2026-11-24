.amdgcn_target "amdgcn-amd-amdhsa--gfx1030"
.text
.globl fminmax_probe
.p2align 8
.type fminmax_probe,@function
fminmax_probe:
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)

    s_mov_b32 s12, exec_lo
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)

    v_mov_b32_e32 v20, 0x7fc00000    // quiet NaN
    v_mov_b32_e32 v21, 0x40400000    // 3.0
    v_mov_b32_e32 v22, 0x40a00000    // 5.0
    v_mov_b32_e32 v23, 0x40e00000    // 7.0
    v_mov_b32_e32 v24, 1.0
    v_mov_b32_e32 v10, 0             // global offset and LDS address

    // Global memory words 4-9, the open question: initial values, then one atomic each (no return).
    global_store_dword v10, v24, s[4:5] offset:16    // fmin: memory 1.0, data NaN
    global_store_dword v10, v20, s[4:5] offset:20    // fmin: memory NaN, data 1.0
    global_store_dword v10, v22, s[4:5] offset:24    // fmin: memory 5.0, data 3.0
    global_store_dword v10, v24, s[4:5] offset:28    // fmax: memory 1.0, data NaN
    global_store_dword v10, v20, s[4:5] offset:32    // fmax: memory NaN, data 1.0
    global_store_dword v10, v21, s[4:5] offset:36    // fmax: memory 3.0, data 5.0
    s_waitcnt_vscnt null, 0
    global_atomic_fmin v10, v20, s[4:5] offset:16
    global_atomic_fmin v10, v24, s[4:5] offset:20
    global_atomic_fmin v10, v21, s[4:5] offset:24
    global_atomic_fmax v10, v20, s[4:5] offset:28
    global_atomic_fmax v10, v24, s[4:5] offset:32
    global_atomic_fmax v10, v22, s[4:5] offset:36

    // LDS words 0-7: the same cases through ds_min/max_f32, whose NaN handling was already
    // measured on gfx1036 (Marvisak/VIctory#628). Initial values, one atomic each, then read back.
    ds_write_b32 v10, v24 offset:0     // min: memory 1.0, data NaN
    ds_write_b32 v10, v20 offset:4     // min: memory NaN, data 1.0
    ds_write_b32 v10, v22 offset:8     // min: memory 5.0, data 3.0
    ds_write_b32 v10, v22 offset:12    // min: memory 5.0, data 7.0
    ds_write_b32 v10, v24 offset:16    // max: memory 1.0, data NaN
    ds_write_b32 v10, v20 offset:20    // max: memory NaN, data 1.0
    ds_write_b32 v10, v21 offset:24    // max: memory 3.0, data 5.0
    ds_write_b32 v10, v22 offset:28    // max: memory 5.0, data 3.0
    s_waitcnt lgkmcnt(0)
    ds_min_f32 v10, v20 offset:0
    ds_min_f32 v10, v24 offset:4
    ds_min_f32 v10, v21 offset:8
    ds_min_f32 v10, v23 offset:12
    ds_max_f32 v10, v20 offset:16
    ds_max_f32 v10, v24 offset:20
    ds_max_f32 v10, v22 offset:24
    ds_max_f32 v10, v21 offset:28
    s_waitcnt lgkmcnt(0)
    ds_read_b128 v[12:15], v10 offset:0
    ds_read_b128 v[16:19], v10 offset:16
    s_waitcnt lgkmcnt(0)

    // Only lane 0 writes the result, before restoring the initial EXEC.
    v_mov_b32_e32 v11, s12
    global_store_dword v10, v11, s[4:5]
    global_store_dwordx4 v10, v[12:15], s[4:5] offset:48
    global_store_dwordx4 v10, v[16:19], s[4:5] offset:64
    s_waitcnt_vscnt null, 0
    s_mov_b32 exec_lo, s12
    s_endpgm
.Lfminmax_probe_end:
.size fminmax_probe, .Lfminmax_probe_end-fminmax_probe

.section .rodata
.p2align 6
.amdhsa_kernel fminmax_probe
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 25
    .amdhsa_next_free_sgpr 13
    .amdhsa_group_segment_fixed_size 32
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
  - .name: fminmax_probe
    .symbol: fminmax_probe.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 32
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 25
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
