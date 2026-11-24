.amdgcn_target "amdgcn-amd-amdhsa--gfx1036"
.text
.globl bpermute_probe
.p2align 8
.type bpermute_probe,@function
bpermute_probe:
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)

    // Number each active lane of the physical wave.
    v_mbcnt_lo_u32_b32 v0, -1, 0
    v_mbcnt_hi_u32_b32 v8, -1, v0
    v_or_b32_e32 v2, 0xa5000000, v8
    v_and_b32_e32 v1, 31, v8
    v_xor_b32_e32 v1, 1, v1
    v_lshlrev_b32_e32 v1, 2, v1
    v_or_b32_e32 v3, 128, v1

    ds_bpermute_b32 v9, v1, v2
    ds_bpermute_b32 v10, v3, v2
    s_waitcnt lgkmcnt(0)

    // Interleaved results: lane, low address, bit-7 address, full-EXEC check.
    s_and_b32 s6, exec_lo, exec_hi
    v_mov_b32_e32 v11, s6
    v_lshlrev_b32_e32 v4, 4, v8
    global_store_dwordx4 v4, v[8:11], s[4:5]
    s_waitcnt_vscnt null, 0
    s_endpgm
.Lbpermute_probe_end:
.size bpermute_probe, .Lbpermute_probe_end-bpermute_probe

.section .rodata
.p2align 6
.amdhsa_kernel bpermute_probe
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 12
    .amdhsa_next_free_sgpr 7
    .amdhsa_group_segment_fixed_size 0
    .amdhsa_private_segment_fixed_size 0
    .amdhsa_kernarg_size 8
    .amdhsa_wavefront_size32 0
.end_amdhsa_kernel

.amdgpu_metadata
---
amdhsa.version: [ 1, 2 ]
amdhsa.target: amdgcn-amd-amdhsa--gfx1036
amdhsa.kernels:
  - .name: bpermute_probe
    .symbol: bpermute_probe.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 64
    .sgpr_count: 7
    .vgpr_count: 12
    .max_flat_workgroup_size: 64
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
