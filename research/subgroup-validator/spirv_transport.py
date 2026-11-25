# SPDX-License-Identifier: MIT
"""Conservatively recognize one local, typed SPIR-V subgroup transport form."""

from dataclasses import dataclass
from collections import defaultdict

from lane_contract import Domain, Guest, LaneBase, Lowering, Participation, check


class UnsupportedPattern(ValueError):
    """The recognized SPIR-V fragment differs from the model's contract."""


@dataclass(frozen=True)
class Instruction:
    ident: str | None
    opcode: str
    args: tuple[str, ...]
    block: str | None
    line: int


class Module:
    def __init__(self, assembly: str):
        self.definitions = {}
        self.instructions = []
        self.users = defaultdict(list)
        self.block_functions = {}
        block = None
        function = None
        for line, raw in enumerate(assembly.splitlines(), 1):
            parts = raw.partition(";")[0].split()
            if not parts:
                continue
            ident = None
            if len(parts) >= 3 and parts[1] == "=":
                ident, _, *parts = parts
            opcode, *args = parts
            if opcode == "OpFunction":
                function = ident
            if opcode == "OpLabel":
                block = ident
                self.block_functions[block] = function
            if opcode == "OpFunctionEnd":
                block = None
                function = None
            insn = Instruction(ident, opcode, tuple(args), block, line)
            self.instructions.append(insn)
            if ident:
                require(ident not in self.definitions, f"duplicate definition {ident}")
                self.definitions[ident] = insn
            for arg in args:
                if arg.startswith("%"):
                    self.users[arg].append(insn)

    def operands(self, ident, opcode, arity, *, block=None):
        insn = self.definitions.get(ident)
        require(insn is not None and insn.opcode == opcode and len(insn.args) == arity,
                f"expected {opcode} on {ident}")
        require(block is None or insn.block == block, f"{ident} is outside the local basic block")
        return insn.args

    def use(self, ident, opcode, arity, *, block):
        users = self.users[ident]
        require(len(users) == 1, f"expected exactly one use of {ident}")
        insn = users[0]
        require(insn.opcode == opcode and len(insn.args) == arity and insn.block == block,
                f"expected local {opcode} consuming {ident}")
        return insn

    def uint_constant(self, ident, uint):
        kind, literal = self.operands(ident, "OpConstant", 2)
        require(kind == uint, f"expected unsigned 32-bit constant on {ident}")
        try:
            return int(literal, 0)
        except ValueError as exc:
            raise UnsupportedPattern(f"unsupported literal for {ident}") from exc


def require(condition, reason):
    if not condition:
        raise UnsupportedPattern(reason)


def recognize(module: Module, shuffle: Instruction):
    """Bind the selector, ballot, source guard and write-back by SSA identity."""
    uint, scope, input_value, selected = shuffle.args
    block = shuffle.block
    require(block is not None, "shuffle has no basic block")
    require(module.operands(uint, "OpTypeInt", 2) == ("32", "0"), "shuffle must carry u32")
    require(module.uint_constant(scope, uint) == 3, "shuffle must use Subgroup scope")

    select_type, present, desired, self_index = module.operands(selected, "OpSelect", 4, block=block)
    boolean, extract_scope, ballot, ballot_index = module.operands(
        present, "OpGroupNonUniformBallotBitExtract", 4, block=block)
    module.operands(boolean, "OpTypeBool", 0)
    ballot_type, ballot_scope, predicate = module.operands(ballot, "OpGroupNonUniformBallot", 3, block=block)
    require(module.operands(ballot_type, "OpTypeVector", 2) == (uint, "4"), "ballot requires four u32 words")
    require(module.operands(predicate, "OpConstantTrue", 1) == (boolean,), "ballot must reflect host participation")
    require(select_type == uint and ballot_index == desired and scope == ballot_scope == extract_scope,
            "shuffle fallback must test participation of the desired lane")

    lane_type, lane_pointer = module.operands(self_index, "OpLoad", 2, block=block)
    require(lane_type == uint and any(
        insn.opcode == "OpDecorate" and insn.args == (lane_pointer, "BuiltIn", "SubgroupLocalInvocationId")
        for insn in module.users[lane_pointer]
    ), "missing subgroup-local fallback lane")
    result_type, base, selector = module.operands(desired, "OpBitwiseOr", 3, block=block)
    base_type, base_lane, base_mask = module.operands(base, "OpBitwiseAnd", 3, block=block)
    selector_type, shifted, index_mask = module.operands(selector, "OpBitwiseAnd", 3, block=block)
    shift_type, addr, bits = module.operands(shifted, "OpShiftRightLogical", 3, block=block)
    add_type, address_input, offset = module.operands(addr, "OpIAdd", 3, block=block)
    require(all(kind == uint for kind in (result_type, base_type, selector_type, shift_type, add_type)),
            "lane calculation requires unsigned 32-bit operands")
    require(base_lane == self_index and module.uint_constant(index_mask, uint) == 31
            and module.uint_constant(bits, uint) == 2, "unsupported subgroup selector")
    base_bits = module.uint_constant(base_mask, uint)
    require(base_bits in (0, 32), "unmodeled partition base")
    offset_bytes = module.uint_constant(offset, uint)

    source_type, guest_active, data_input, inactive_zero = module.operands(input_value, "OpSelect", 4, block=block)
    require(source_type == uint and module.uint_constant(inactive_zero, uint) == 0,
            "source must be zeroed when its guest lane is inactive")
    # The source and address producers and the guest EXEC snapshot are bound inputs.
    # They are not interpreted by this fragment or assumed to be independent in an upstream shader.
    require(address_input in module.definitions and data_input in module.definitions, "missing fragment input")
    guest_active_def = module.definitions.get(guest_active)
    require(guest_active_def is not None and guest_active_def.args[:1] == (boolean,),
            "guest active flag must be a boolean SSA value")

    mask_result = module.use(shuffle.ident, "OpBitwiseAnd", 3, block=block)
    require(mask_result.args[:2] == (uint, shuffle.ident), "unsupported shuffle result mask order")
    mask_type, mask_guard, mask_full, mask_zero = module.operands(mask_result.args[2], "OpSelect", 4, block=block)
    require(mask_type == uint and mask_guard == present and module.uint_constant(mask_full, uint) == 0xffffffff
            and module.uint_constant(mask_zero, uint) == 0, "absent host source must produce zero")

    new_bits = module.use(mask_result.ident, "OpBitwiseAnd", 3, block=block)
    require(new_bits.args[:2] == (uint, mask_result.ident), "unsupported new destination result")
    exec_mask = new_bits.args[2]
    require(module.operands(exec_mask, "OpSelect", 4, block=block) == (uint, guest_active, mask_full, mask_zero),
            "destination guard must use the same guest EXEC value as the source guard")
    write_back = module.use(new_bits.ident, "OpBitwiseOr", 3, block=block)
    require(write_back.args[:2] == (uint, new_bits.ident), "unsupported destination write-back")
    old_type, old, complement = module.operands(write_back.args[2], "OpBitwiseAnd", 3, block=block)
    require(old_type == uint and module.operands(complement, "OpNot", 2, block=block) == (uint, exec_mask),
            "inactive destination must keep old bits")
    old_type, slot = module.operands(old, "OpLoad", 2, block=block)
    store = module.use(write_back.ident, "OpStore", 2, block=block)
    require(old_type == uint and store.args == (slot, write_back.ident), "old and written registers differ")
    register = module.definitions.get(slot)
    if register is not None and register.opcode == "OpAccessChain" and len(register.args) == 3:
        _, storage, index = register.args
        module.uint_constant(index, uint)
        register = module.definitions.get(storage)
    require(register is not None and register.opcode == "OpVariable" and register.args[1:2] == ("Function",),
            "destination must be a function-local variable or its constant element")
    old_load = module.definitions[old]
    value_operations = {"OpBitwiseAnd", "OpBitwiseOr", "OpNot", "OpSelect"}
    require(all(insn.opcode in value_operations for insn in module.instructions
                if old_load.line < insn.line < store.line), "unmodeled operation between old-register load and store")

    base = LaneBase.PARTITION if base_bits == 32 else LaneBase.HOST
    bindings = {"address_input": address_input, "offset_bytes": offset_bytes, "data_input": data_input,
                "guest_active": guest_active, "old_value": old, "destination": slot}
    return Lowering(32, guest_guard=True, host_guard=True, lane_base=base), store.line, bindings


def inspect(assembly: str) -> dict:
    module = Module(assembly)
    entries = [insn.args for insn in module.instructions if insn.opcode == "OpEntryPoint"]
    require(len(entries) == 1 and len(entries[0]) >= 3 and entries[0][0] == "GLCompute",
            "expected one compute entry point")
    reports = []
    for insn in module.instructions:
        if insn.opcode != "OpGroupNonUniformShuffle" or len(insn.args) != 4:
            continue
        entry = {"shuffle": insn.ident, "line": insn.line}
        try:
            require(module.block_functions.get(insn.block) == entries[0][1], "shuffle outside the compute entry")
            lowering, store_line, bindings = recognize(module, insn)
        except UnsupportedPattern as exc:
            entry.update({"status": "unmodeled", "reason": str(exc)})
        else:
            entry.update({"status": "recognized", "store_line": store_line, "bindings": bindings, "checks": {
                f"{physical}/{participation}": check(Guest(32), lowering, Domain(64, physical, participation))
                for physical in (32, 64)
                for participation in (Participation.SUPERSET, Participation.INDEPENDENT)
            }})
        reports.append(entry)
    return {"shuffles": reports}
