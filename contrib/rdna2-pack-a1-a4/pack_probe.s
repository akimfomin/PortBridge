// SPDX-License-Identifier: MIT
.amdgcn_target "amdgcn-amd-amdhsa--gfx1030"
.text
.globl pack_probe
.p2align 8
.type pack_probe,@function

// Keep the exact documented two-source encodings requested in issue #84:
// 0xd76a0000 = v_cvt_pk_u16_u32, 0xd76b0000 = v_cvt_pk_i16_i32.
// LLVM 23 uses inline zero in the unused source field instead of zero bits.
.macro run_pack offset, tag, opcode, input0, input1
    v_mov_b32_e32 v0, 0xa5a5a5a5
    v_mov_b32_e32 v1, \input0
    v_mov_b32_e32 v2, \input1
    .long \opcode, 0x00020501
    v_mov_b32_e32 v1, \tag
    global_store_dwordx2 v4, v[0:1], s[4:5] offset:\offset
.endm

pack_probe:
    s_load_dwordx2 s[4:5], s[0:1], 0
    s_waitcnt lgkmcnt(0)
    s_mov_b32 s12, exec_lo
    s_mov_b32 exec_lo, 1
    s_waitcnt_depctr depctr_sa_sdst(0)
    v_mov_b32_e32 v4, 0
    v_mov_b32_e32 v0, s12
    v_mov_b32_e32 v1, 0x50420000
    global_store_dwordx2 v4, v[0:1], s[4:5]
    run_pack  8, 0x50420001, 0xd76a0000, 0xabc,      0x123
    run_pack 16, 0x50420002, 0xd76a0000, 0x00010000, 0x00001234
    run_pack 24, 0x50420003, 0xd76a0000, 0x80000001, 0x00000005
    run_pack 32, 0x50420004, 0xd76b0000, 0xffff0000, 0x00008000
    run_pack 40, 0x50420005, 0xd76b0000, 0x00012345, 0xffff7fff
    s_waitcnt_vscnt null, 0
    s_mov_b32 exec_lo, s12
    s_endpgm
.Lpack_probe_end:
.size pack_probe, .Lpack_probe_end-pack_probe

.section .rodata
.p2align 6
.amdhsa_kernel pack_probe
    .amdhsa_user_sgpr_kernarg_segment_ptr 1
    .amdhsa_next_free_vgpr 5
    .amdhsa_next_free_sgpr 13
    .amdhsa_group_segment_fixed_size 0
    .amdhsa_private_segment_fixed_size 0
    .amdhsa_kernarg_size 8
    .amdhsa_wavefront_size32 1
    .amdhsa_ieee_mode 1
.end_amdhsa_kernel

.amdgpu_metadata
---
amdhsa.version: [1, 2]
amdhsa.target: amdgcn-amd-amdhsa--gfx1030
amdhsa.kernels:
  - .name: pack_probe
    .symbol: pack_probe.kd
    .kernarg_segment_size: 8
    .kernarg_segment_align: 8
    .group_segment_fixed_size: 0
    .private_segment_fixed_size: 0
    .wavefront_size: 32
    .sgpr_count: 13
    .vgpr_count: 5
    .max_flat_workgroup_size: 32
    .args:
      - .name: out
        .size: 8
        .offset: 0
        .value_kind: global_buffer
        .address_space: global
...
.end_amdgpu_metadata
