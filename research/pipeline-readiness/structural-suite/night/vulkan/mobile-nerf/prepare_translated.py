# SPDX-License-Identifier: MIT
"""Prepare the bounded Mobile NeRF fragment fixtures (Vulkan 1.3)."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_probe import reflect

FRAGMENTS = {
    "d509467c9b2c18b392bf8970993cd551788f013ad5130a381211c969cebce0d0": "nerf71-whole",
    "7ee8b474ad50167516f003a23f8f9ab995f6e994e75f16ad0b2eae83b650dbee": "nerf73-whole",
    "ee8b222654003f23450365d2f6d8191e09b865c15f24a26d9b1fed1e679b5be1": "nerf71-strict",
    "9c31c98fbfee86cdd7b5d58dbb6ad179c08e030a57c684736da0221ebcb56948": "nerf73-strict",
    "d5854270922a7aae6cf01a3dee5d09366158081488d10a8b44891d98e869718d": "nerf71-gamma",
    "4f5a97441c987fa9449a390c37df92f6b82ae2f298ec0f924015a6052513798c": "nerf73-gamma",
}


def must(test, msg):
    if not test:
        raise ValueError(msg)


def rewrite(text, track):
    lines = text.splitlines()
    defs = {
        p[0]: p[2:] for line in lines if len(p := line.split()) >= 4 and p[1] == "="
    }

    def operands(v, op, ty=None):
        args = defs[v]
        must(args[0] == op and (ty is None or args[1] == ty), (v, args, op, ty))
        return args[2:] if ty else args[1:]

    def root(value, half):
        load, part = operands(value, "OpCompositeExtract", "%uint")
        must(part == str(half), "wrong root half")
        (ptr,) = operands(load, "OpLoad", "%v2uint")
        return push_index(ptr)

    def push_index(ptr):
        reg, idx = operands(ptr, "OpAccessChain", "%_ptr_PushConstant_v2uint")
        must(reg == "%registers", "wrong root register")
        (index,) = operands(idx, "OpConstant", "%uint")
        return int(index)

    def inspect_v4(v):
        (pair,) = operands(
            v, "OpBitcast", "%_ptr_PhysicalStorageBuffer_PhysicalPointerUint4"
        )
        low, high = operands(pair, "OpCompositeConstruct", "%v2uint")
        carry, part = operands(low, "OpCompositeExtract", "%uint")
        must(part == "0", "missing address low word")
        base, offset = operands(carry, "OpIAddCarry", "%AddCarry")
        root_id = root(base, 0)
        must(root_id in (1, 2, 3, 4), "bad memory window")
        a, b = operands(high, "OpIAdd", "%uint")
        must(
            root(a, 1) == root_id
            and operands(b, "OpCompositeExtract", "%uint") == [carry, "1"],
            "unmatched address words",
        )
        return carry, offset

    count = {}

    def inc(k):
        count[k] = count.get(k, 0) + 1

    bounded = {}
    checked_ptr = set()
    for v, args in defs.items():
        if args[0] == "OpBitcast" and args[1].startswith("%_ptr_PhysicalStorageBuffer"):
            if args[1].endswith("PhysicalPointerUint4"):
                carry, offset = inspect_v4(v)
                bounded[carry] = offset
            else:
                (ptr,) = operands(args[2], "OpLoad", "%v2uint")
                must(
                    args[1].endswith("PhysicalPointerUintArray")
                    and push_index(ptr) == 0,
                    "non-SGPR base",
                )
            checked_ptr.add(v)
    must(len(bounded) > 0, "no window loads")
    for v, args in defs.items():
        if args[0] != "OpInBoundsAccessChain" or not args[1].startswith(
            "%_ptr_PhysicalStorageBuffer"
        ):
            continue
        must(
            args[2] in checked_ptr and args[3] == "%uint_0",
            "unrecognized physical memory source",
        )
        if args[1].endswith("_v4uint"):
            must(len(args) == 4, "unexpected vector pointer")
        else:
            must(
                args[1].endswith("_uint")
                and len(args) == 5
                and int(operands(args[4], "OpConstant", "%uint")[0]) < 128,
                "SGPR OOB",
            )
        inc("bounded_load_ptr")
    for op in (
        "OpConvertUToPtr",
        "OpPtrAccessChain",
        "OpInBoundsPtrAccessChain",
        "OpCopyMemory",
        "OpAtomic",
        "OpImageWrite",
    ):
        must(op not in text, "unexpected pointer operation: " + op)
    must(
        text.count(" Aligned|NonPrivatePointer 4") == count["bounded_load_ptr"],
        "unexpected physical memory effects",
    )
    decorations = []
    output = []
    decl = [
        "%pb_max = OpConstant %uint 16368",
        "%pb_seven = OpConstant %uint 7",
        "%pb_align = OpConstant %uint 4294967292",
        "%pb_lutlen = OpConstant %uint 78",
    ]
    if track:
        decl.extend(
            [
                "%pb_six = OpConstant %uint 6",
                "%pb_bool_ptr = OpTypePointer Private %bool",
                "%pb_false = OpConstantFalse %bool",
                "%pb_bad_alpha = OpConstant %float -7",
                "%pb_fault = OpVariable %pb_bool_ptr Private %pb_false",
            ]
        )

    def fault(valid, ident):
        if track:
            output.extend(
                [
                    f"%pb_inv{ident} = OpLogicalNot %bool {valid}",
                    f"%pb_prev{ident} = OpLoad %bool %pb_fault",
                    f"%pb_bad{ident} = OpLogicalOr %bool %pb_prev{ident} %pb_inv{ident}",
                    f"OpStore %pb_fault %pb_bad{ident}",
                ]
            )

    inserted = False
    for line in lines:
        s = line.split()
        if not s:
            continue
        if s[0] == "OpDecorate" and s[2:4] == ["Binding", "0"]:
            must(s[1] in ("%13", "%18", "%23"), "unrecognized alias")
            line = (
                "OpDecorate "
                + s[1]
                + " Binding "
                + str(("%13", "%18", "%23").index(s[1]))
            )
        if track and s[0] == "OpEntryPoint":
            line += " %pb_fault"
        if not inserted and len(s) >= 4 and s[2] == "OpFunction":
            output.extend(decl)
            inserted = True
        ident = s[0].lstrip("%")
        if s[0] in bounded:
            offset = bounded[s[0]]
            output.extend(
                [
                    f"%pb_aligned{ident} = OpBitwiseAnd %uint {offset} %pb_align",
                    f"%pb_valid{ident} = OpULessThanEqual %bool {offset} %pb_max",
                    f"%pb_safe{ident} = OpSelect %uint %pb_valid{ident} %pb_aligned{ident} %uint_0",
                ]
            )
            if track:
                output.extend(
                    [
                        f"%pb_eq{ident} = OpIEqual %bool {offset} %pb_aligned{ident}",
                        f"%pb_checked{ident} = OpLogicalAnd %bool %pb_eq{ident} %pb_valid{ident}",
                    ]
                )
                fault(f"%pb_checked{ident}", ident)
            line = " ".join([*s[:-1], f"%pb_safe{ident}"])
            inc("window_offsets")
        if (
            len(s) >= 6
            and s[2] == "OpAccessChain"
            and s[3].startswith("%_ptr_UniformConstant")
        ):
            must(s[4] in ("%13", "%18", "%23") and len(s) == 6, "unknown descriptor")
            output.append(f"%pb_index{ident} = OpBitwiseAnd %uint {s[5]} %pb_seven")
            decorations.append(f"OpDecorate %pb_index{ident} NonUniform")
            if track:
                # The fixture assigns only unsigned slot 6 and float slots 0, 2, 4.
                # Signed or fallback descriptors must not source any observable pixel.
                if s[4] == "%13":
                    output.append(f"%pb_ivalid{ident} = OpIEqual %bool {s[5]} %pb_six")
                elif s[4] == "%18":
                    output.append(f"%pb_ivalid{ident} = OpCopyObject %bool %pb_false")
                else:
                    output.extend(
                        [
                            f"%pb_evenbits{ident} = OpBitwiseAnd %uint {s[5]} %uint_1",
                            f"%pb_even{ident} = OpIEqual %bool %pb_evenbits{ident} %uint_0",
                            f"%pb_frange{ident} = OpULessThanEqual %bool {s[5]} %uint_4",
                            f"%pb_ivalid{ident} = OpLogicalAnd %bool %pb_even{ident} %pb_frange{ident}",
                        ]
                    )
                fault(f"%pb_ivalid{ident}", ident)
            line = " ".join([*s[:-1], f"%pb_index{ident}"])
            inc("image_accesses")
        if (
            len(s) >= 6
            and s[2] == "OpInBoundsAccessChain"
            and s[3] == "%_ptr_Private_uint"
        ):
            must(
                len(s) == 6 and defs[s[4]][1] == "%_ptr_Private__arr_uint_uint_78",
                "unrecognized private array",
            )
            output.extend(
                [
                    f"%pb_lvalid{ident} = OpULessThan %bool {s[5]} %pb_lutlen",
                    f"%pb_lookup{ident} = OpSelect %uint %pb_lvalid{ident} {s[5]} %uint_0",
                ]
            )
            fault(f"%pb_lvalid{ident}", ident)
            line = " ".join([*s[:-1], f"%pb_lookup{ident}"])
            inc("lookup_accesses")
        if track and s[0] == "OpStore" and defs[s[1]][-1] == "%uint_3":
            must(defs[s[1]][-2] == "%SV_Target", "unexpected alpha target")
            output.extend(
                [
                    "%pb_exit_bad = OpLoad %bool %pb_fault",
                    f"%pb_exit_alpha = OpSelect %float %pb_exit_bad %pb_bad_alpha {s[2]}",
                ]
            )
            line = f"OpStore {s[1]} %pb_exit_alpha"
            inc("fault_outputs")
        output.append(line)
    must(
        inserted
        and count.get("image_accesses") == 12
        and count.get("lookup_accesses") == 4,
        "unexpected declarations",
    )
    if track:
        must(count.get("fault_outputs") == 1, "missing diagnostic")
    at = next(i for i, x in enumerate(output) if "OpDecorate" in x)
    output[at:at] = decorations
    return "\n".join(output) + "\n", count


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fragment", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--tools", type=Path, required=True)
    p.add_argument("--diagnostics", action="store_true")
    args = p.parse_args()
    digest = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
    name = FRAGMENTS[digest(args.fragment)]
    exe = lambda n: str(args.tools / (n + ".exe" if sys.platform == "win32" else n))
    reflect(args.fragment, "xcl-nerf-roots", exe("spirv-dis"), exe("spirv-val"))
    ir = subprocess.check_output(
        [exe("spirv-dis"), args.fragment], text=True, timeout=30
    )
    patched, counts = rewrite(ir, args.diagnostics)
    subprocess.run(
        [exe("spirv-as"), "--target-env", "vulkan1.3", "-", "-o", args.output],
        input=patched,
        text=True,
        check=True,
        timeout=30,
    )
    subprocess.run(
        [exe("spirv-val"), "--target-env", "vulkan1.3", args.output],
        check=True,
        timeout=30,
    )
    print(
        json.dumps(
            {
                "input": name,
                "source_sha": digest(args.fragment),
                "output_sha": digest(args.output),
                "diagnostics": args.diagnostics,
                "counts": counts,
            }
        )
    )


if __name__ == "__main__":
    main()
