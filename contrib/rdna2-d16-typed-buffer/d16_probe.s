// SPDX-License-Identifier: MIT
.amdgcn_target "amdgcn-amd-amdhsa--gfx1030"
.text
.globl d16_probe
.p2align 8
.type d16_probe,@function

// The data allocation contains one four-byte slot for each case. Set the
// pointer in V# to that slot, so the measured MUBUF word always has offset 0.
.macro run_case row, format
    s_mov_b32 s7, \format
    v_mov_b32_e32 v0, 0xa5a5a5a5
    .long 0xe2000000, 0x80010000
    s_waitcnt vmcnt(0)
    v_mov_b32_e32 v1, (0x44313600 + \row)
    global_store_dwordx2 v4, v[0:1], s[8:9] offset:(8 * \row)
    s_add_u32 s4, s4, 4
    s_addc_u32 s5, s5, 0
.endm

d16_probe:
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_load_dwordx2 s[8:9], s[0:1], 8
    s_waitcnt lgkmcnt(0)
    s_mov_b32 s12, exec_lo
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)
    s_mov_b32 s6, 4
    v_mov_b32_e32 v4, 0
    v_mov_b32_e32 v0, s12
    v_mov_b32_e32 v1, 0x44313600
    global_store_dwordx2 v4, v[0:1], s[8:9]

    run_case  1, 0x31007004
    run_case  2, 0x31007004
    run_case  3, 0x31008004
    run_case  4, 0x31008004
    run_case  5, 0x31007004
    run_case  6, 0x31016004
    run_case  7, 0x31016004
    run_case  8, 0x31016004
    run_case  9, 0x31016004
    run_case 10, 0x31016004
    run_case 11, 0x31016004
    run_case 12, 0x31016004
    run_case 13, 0x31016004
    run_case 14, 0x3100d004
    run_case 15, 0x31009004
    run_case 16, 0x31009004
    run_case 17, 0x31014004

    s_waitcnt_vscnt null, 0
    s_mov_b32 exec_lo, s12
    s_endpgm
.Ld16_probe_end:
.size d16_probe, .Ld16_probe_end-d16_probe

.section .rodata
.p2align 6
.amdhsa_kernel d16_probe
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 5
    .amdhsa_next_free_sgpr 13
    .amdhsa_group_segment_fixed_size 0
    .amdhsa_private_segment_fixed_size 0
    .amdhsa_kernarg_size 16
    .amdhsa_wavefront_size32 1
    .amdhsa_ieee_mode 1
.end_amdhsa_kernel

.amdgpu_metadata
---
amdhsa.version: [1, 2]
amdhsa.target: amdgcn-amd-amdhsa--gfx1030
amdhsa.kernels:
  - .name: d16_probe
    .symbol: d16_probe.kd
    .kernarg_segment_size: 16
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 5
    .max_flat_workgroup_size: 32
    .args:
      - .name: input
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
      - .name: output
        .size: 8
        .offset: 8
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
