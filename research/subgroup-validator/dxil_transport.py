# SPDX-License-Identifier: MIT
"""Recognize the pinned plain Direct DXIL compute half-wave fixture."""

import re

from lane_contract import Domain, Guest, LaneBase, Lowering, Participation, check


VALUE = r"%[-.\w]+"
WORD = rf"(?:{VALUE}|-?\d+)"
SHUFFLE = rf"call i32 @dx\.op\.waveReadLaneAt\.i32\(i32 117, i32 ({VALUE}), i32 ({VALUE})\)"
EXTRACT = rf"extractvalue %dx\.types\.ResRet\.i32 ({VALUE}), 0"
RAW_LOAD = rf"call %dx\.types\.ResRet\.i32 @dx\.op\.rawBufferLoad\.i32\(i32 139, %dx\.types\.Handle ({VALUE}), i32 ({WORD}), i32 undef, i8 1, i32 4\)"
RAW_STORE = rf"call void @dx\.op\.rawBufferStore\.i32\(i32 140, %dx\.types\.Handle ({VALUE}), i32 ({WORD}), i32 undef, i32 ({WORD}), i32 undef, i32 undef, i32 undef, i8 1, i32 4\)"
ANNOTATE = rf"call %dx\.types\.Handle @dx\.op\.annotateHandle\(i32 216, %dx\.types\.Handle ({VALUE}), %dx\.types\.ResourceProperties \{{ i32 4107, i32 0 \}}\)"
HANDLE = r"call %dx\.types\.Handle @dx\.op\.createHandleFromBinding\(i32 217, %dx\.types\.ResBind \{ i32 (\d+), i32 (\d+), i32 0, i8 1 \}, i32 (\d+), i1 false\)"


class UnsupportedDxil(ValueError):
    pass


def require(predicate, reason):
    if not predicate:
        raise UnsupportedDxil(reason)


class Listing:
    """Index the specific SSA grammar consumed by this adapter."""

    def __init__(self, text):
        self.defs = {}
        self.stores = []
        self.terminators = {}
        self.unknown_store_blocks = set()
        self.users = {}
        block = "entry"
        functions = []
        for line_number, raw in enumerate(text.splitlines(), 1):
            if marker := re.match(r"\s*;\s*<label>:(\d+)", raw):
                block = marker[1]
            line = raw.partition(";")[0].strip()
            if line.startswith("define "):
                functions.append(line)
            if line.startswith(("br ", "ret ")):
                require(block not in self.terminators, f"unexpected terminator for block {block}")
                self.terminators[block] = line
            if match := re.fullmatch(rf"({VALUE}) = (.+)", line):
                name, expr = match.groups()
                require(name not in self.defs, f"duplicate identifier {name}")
                self.defs[name] = (expr, block, line_number)
                for value in set(re.findall(VALUE, expr)):
                    self.users.setdefault(value, []).append(name)
            if store := re.fullmatch(RAW_STORE, line):
                self.stores.append((*store.groups(), block, line_number))
            elif re.match(rf"(?:{VALUE} = )?(?:store|atomicrmw|cmpxchg) ", line) or (
                "call " in line and re.search(r"@dx\.op\.(?:rawBufferStore|bufferStore|textureStore|atomic)", line)
            ):
                self.unknown_store_blocks.add(block)
        require(len(functions) == 1 and "@main()" in functions[0], "expected one compute main function")

    def expect(self, ident, pattern, block=None):
        expr, actual_block, _ = self.defs.get(ident, ("", None, None))
        match = re.fullmatch(pattern, expr)
        require(match and (block is None or actual_block == block), f"unsupported {ident}: {expr}")
        return match.groups()

    def unique_user(self, ident, pattern, block):
        values = self.users.get(ident, [])
        require(len(values) == 1, f"expected one SSA use of {ident}")
        user, = values
        return user, self.expect(user, pattern, block)

    def handle_binding(self, handle):
        base, = self.expect(handle, ANNOTATE)
        lo, hi, index = self.expect(base, HANDLE)
        require(lo == hi == index, "unmodeled register-buffer binding")
        return int(lo)

    def raw_source(self, ident):
        raw, = self.expect(ident, EXTRACT)
        handle, address = self.expect(raw, RAW_LOAD)
        return handle, address

    def register(self, address, lane):
        base, displacement = self.expect(address, rf"add i32 ({VALUE}), (\d+)")
        offset = 0
        if not re.fullmatch(rf"mul i32 {VALUE}, 1024", self.defs[base][0]):
            base, = self.expect(base, rf"add i32 ({VALUE}), 512")
            offset = int(displacement)
        else:
            require(displacement == "512", "missing scalar register prefix")
        require(self.expect(base, rf"mul i32 ({VALUE}), 1024") == (lane,), "register belongs to another lane")
        require(0 <= offset < 1024 and offset % 4 == 0, "register displacement exceeds its lane allocation")
        return offset // 4

    def output_path(self, start, end):
        """Check all textual exits from the local slice reach the return block."""
        pending = [(start, frozenset())]
        while pending:
            block, visited = pending.pop()
            require(block not in visited and block not in self.unknown_store_blocks,
                    "loop or unsupported output store on the path from transport to final store")
            terminator = self.terminators.get(block, "")
            if block == end:
                require(terminator == "ret void", "expected terminal register-output block")
                continue
            targets = re.fullmatch(r"br (?:i1 %[-.\w]+, label %(\d+), )?label %(\d+)", terminator)
            require(targets, "an unmodeled path does not reach the final register store")
            pending.extend((b, visited | {block}) for b in targets.groups() if b is not None)

    def output_register_writes(self, lane, reg):
        matching = 0
        for handle, slot, *_ in self.stores:
            if self.handle_binding(handle) != 1:
                continue
            if slot.startswith("%"):
                matching += self.register(slot, lane) == reg
            else:
                offset = int(slot)
                require(0 <= offset < 512 and offset % 4 == 0, "literal store outside the scalar prefix")
        return matching

    def exec_bindings(self, hi, lo, input_handle):
        if hi.startswith("%") and lo.startswith("%"):
            require(self.raw_source(hi) == (input_handle, "508") and
                    self.raw_source(lo) == (input_handle, "504"), "guest EXEC words use unexpected input slots")
            return {"kind": "input-u0", "hi_byte_offset": 508, "lo_byte_offset": 504}
        require((hi, lo) == ("-1431655766", "1431655765"), "unexpected literal guest EXEC pair")
        return {"kind": "literal", "hi": "0xaaaaaaaa", "lo": "0x55555555"}


def exec_bit(ir: Listing, condition, block=None):
    bit, = ir.expect(condition, rf"icmp ne i32 ({VALUE}), 0", block)
    shifted, = ir.expect(bit, rf"and i32 ({VALUE}), 1", block)
    word, position = ir.expect(shifted, rf"lshr i32 ({VALUE}), ({VALUE})", block)
    high, hi, lo = ir.expect(word, rf"select i1 ({VALUE}), i32 ({WORD}), i32 ({WORD})", block)
    lane, = ir.expect(high, rf"icmp uge i32 ({VALUE}), 32", block)
    bit_lane, = ir.expect(position, rf"and i32 ({VALUE}), 31", block)
    require(lane == bit_lane, "EXEC word and bit used different lanes")
    return lane, hi, lo


def decode(ir: Listing, result, data, host_source, physical):
    _, block, line = ir.defs[result]
    source = host_source
    if physical == 32:
        source, = ir.expect(host_source, rf"and i32 ({VALUE}), 31", block)
    half, index = ir.expect(source, rf"or i32 ({VALUE}), ({VALUE})", block)
    lane, base = ir.expect(half, rf"and i32 ({VALUE}), (0|32)", block)
    require(physical == 64 or base == "32", "split guest EXEC must retain the logical half")
    shifted, = ir.expect(index, rf"and i32 ({VALUE}), 31", block)
    address, = ir.expect(shifted, rf"lshr i32 ({VALUE}), 2", block)
    add = re.fullmatch(rf"add i32 ({VALUE}), (\d+)", ir.defs[address][0])
    offset = 0
    if add:
        require(ir.defs[address][1] == block, "byte offset addition outside instruction block")
        address, literal = add.groups()
        offset = int(literal)
    require(offset <= 0xFFFF, "offset must fit guest immediate")
    address_handle, address_slot = ir.raw_source(address)
    data_handle, data_slot = ir.raw_source(data)

    if physical == 64:
        ir.expect(lane, r"call i32 @dx\.op\.flattenedThreadIdInGroup\.i32\(i32 96\)")
    else:
        origin, local = ir.expect(lane, rf"add i32 ({VALUE}), ({VALUE})")
        ir.expect(origin, rf"call i32 @dx\.op\.waveReadLaneFirst\.i32\(i32 118, i32 {VALUE}\)")
        ir.expect(local, r"call i32 @dx\.op\.waveGetLaneIndex\(i32 111\)")

    source_guard_result, (source_on,) = ir.unique_user(
        result, rf"select i1 ({VALUE}), i32 {re.escape(result)}, i32 0", block)
    source_lane, source_hi, source_lo = exec_bit(ir, source_on, block)
    require(source_lane == source, "guest EXEC does not check the selected source")
    write, (destination_on, old) = ir.unique_user(
        source_guard_result, rf"select i1 ({VALUE}), i32 {re.escape(source_guard_result)}, i32 ({VALUE})", block)
    destination_lane, destination_hi, destination_lo = exec_bit(ir, destination_on)
    require((destination_lane, destination_hi, destination_lo) == (lane, source_hi, source_lo),
            "source and write use different guest EXEC snapshots")
    old_handle, old_address = ir.raw_source(old)
    require(address_handle == data_handle == old_handle and ir.handle_binding(old_handle) == 0,
            "guest register inputs must share the test input UAV at u0")
    linked = [(h, addr, block_id, ln) for h, addr, val, block_id, ln in ir.stores if val == write]
    require(len(linked) == 1, "expected one modeled final register store")
    store_handle, store_address, store_block, store_line = linked[0]
    require(ir.handle_binding(store_handle) == 1, "final register store must use the test output UAV at u1")
    require(store_address == old_address, "retained destination and result use different test-register addresses")
    require(store_line > max(line, ir.defs[old][2], ir.defs[write][2]),
            "final register store must follow the selected result")
    ir.output_path(block, store_block)
    destination_register = ir.register(old_address, lane)
    require(ir.output_register_writes(lane, destination_register) == 1,
            "repeated output register write in the fixture")

    base_kind = LaneBase.PARTITION if base == "32" else LaneBase.HOST
    return Lowering(32, lane_base=base_kind), {
        "line": line, "shuffle": result, "offset": offset, "store_line": store_line,
        "input_uav": 0, "output_uav": 1,
        "guest_exec": ir.exec_bindings(source_hi, source_lo, old_handle),
        "address_vgpr": ir.register(address_slot, lane), "data_vgpr": ir.register(data_slot, lane),
        "destination_vgpr": destination_register,
    }


def inspect_dxil(text, physical):
    if physical not in (32, 64):
        raise ValueError("fixture needs a 32- or 64-lane host")
    ir = Listing(text)
    reports = []
    for ident, (expr, _, line) in ir.defs.items():
        if "@dx.op.waveReadLaneAt." not in expr:
            continue
        match = re.fullmatch(SHUFFLE, expr)
        try:
            require(match, "unsupported shuffle type or opcode")
            target, row = decode(ir, ident, *match.groups(), physical)
        except (UnsupportedDxil, KeyError) as exc:
            reports.append({"line": line, "shuffle": ident, "status": "unmodeled", "reason": str(exc)})
            continue
        row["status"] = "recognized"
        row["checks"] = {
            participation.value: check(Guest(32), target, Domain(64, physical, participation))
            for participation in (Participation.SUPERSET, Participation.INDEPENDENT)
        }
        reports.append(row)
    return reports
