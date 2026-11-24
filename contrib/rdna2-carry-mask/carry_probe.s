.amdgcn_target "amdgcn-amd-amdhsa--gfx1036"
.text
.globl carry_probe
.p2align 8
.type carry_probe,@function
carry_probe:
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)

    s_mov_b32 s12, exec_lo
    v_mov_b32_e32 v0, 1
    s_mov_b32 vcc_lo, 0xfffffffe
    s_mov_b32 s40, 0xfffffffe
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)
    v_add_co_ci_u32_e32 v1, vcc_lo, -1, v0, vcc_lo
    s_waitcnt_depctr depctr_va_sdst(0) depctr_va_vcc(0)
    s_mov_b32 s13, vcc_lo
    v_add_co_ci_u32_e64 v2, s40, -1, v0, s40
    s_waitcnt_depctr depctr_va_sdst(0)
    s_mov_b32 s14, s40

    // Known comparison result with the same EXEC and VCC preload.
    s_mov_b32 vcc_lo, 0xfffffffe
    s_waitcnt_depctr depctr_sa_sdst(0)
    v_cmp_eq_u32_e32 vcc_lo, 1, v0
    s_waitcnt_depctr depctr_va_sdst(0) depctr_va_vcc(0)
    s_mov_b32 s15, vcc_lo

    // Only lane 0 writes the result, before restoring the initial EXEC.
    v_mov_b32_e32 v5, 0
    v_mov_b32_e32 v8, s12
    v_mov_b32_e32 v9, v1
    v_mov_b32_e32 v10, v2
    v_mov_b32_e32 v11, s13
    v_mov_b32_e32 v12, s14
    global_store_dwordx4 v5, v[8:11], s[4:5]
    v_mov_b32_e32 v13, s15
    global_store_dwordx2 v5, v[12:13], s[4:5] offset:16
    s_waitcnt_vscnt null, 0
    s_mov_b32 exec_lo, s12
    s_endpgm
.Lcarry_probe_end:
.size carry_probe, .Lcarry_probe_end-carry_probe

.section .rodata
.p2align 6
.amdhsa_kernel carry_probe
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 14
    .amdhsa_next_free_sgpr 41
    .amdhsa_group_segment_fixed_size 0
    .amdhsa_private_segment_fixed_size 0
    .amdhsa_kernarg_size 8
    .amdhsa_wavefront_size32 1
.end_amdhsa_kernel

.amdgpu_metadata
---
amdhsa.version: [ 1, 2 ]
amdhsa.target: amdgcn-amd-amdhsa--gfx1036
amdhsa.kernels:
  - .name: carry_probe
    .symbol: carry_probe.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 41
    .vgpr_count: 14
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
