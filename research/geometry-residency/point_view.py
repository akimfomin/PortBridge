"""Reference semantics for ordered point views across selection and concatenation."""

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import accumulate


MAX_BLOCK_ROWS = 256


def slots(mask):
    """Yield physical slots in ascending order."""
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


@dataclass(frozen=True, slots=True)
class _Block:
    columns: tuple
    mask: int

    @property
    def length(self):
        return len(self.columns[0])


@dataclass(frozen=True, slots=True)
class PointView:
    """An ordered immutable view of points with parallel named attribute columns.

    Blocks share read-only column storage across versions. Operations receive
    their input view's dense Index, which may differ from a physical slot or id.
    Column elements must be immutable. Calling callbacks with side effects is
    outside the contract.
    """

    names: tuple[str, ...]
    _blocks: tuple[_Block, ...]
    _ends: tuple[int, ...] = field(init=False, repr=False)

    def __post_init__(self):
        ends = accumulate(block.mask.bit_count() for block in self._blocks)
        object.__setattr__(self, "_ends", tuple(ends))

    @classmethod
    def from_columns(cls, columns: Mapping, block_rows=MAX_BLOCK_ROWS):
        if not 1 <= block_rows <= MAX_BLOCK_ROWS:
            raise ValueError(f"Block size must be in [1, {MAX_BLOCK_ROWS}]")
        names = tuple(columns)
        if not names or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("At least one named attribute is required")
        values = tuple(tuple(column) for column in columns.values())
        size = len(values[0])
        if any(len(column) != size for column in values):
            raise ValueError("Attributes must have the same length")
        blocks = []
        for start in range(0, size, block_rows):
            stop = min(start + block_rows, size)
            blocks.append(_Block(tuple(column[start:stop] for column in values),
                                 (1 << (stop - start)) - 1))
        return cls(names, tuple(blocks))

    def __len__(self):
        return self._ends[-1] if self._ends else 0

    @property
    def referenced_slots(self):
        """Occupied storage slots referenced by this view, including dead rows.

        Repeated blocks are counted per logical occurrence. This is a
        conservative row-slot bound, rather than actual allocator usage.
        """
        return sum(block.length for block in self._blocks)

    def _column_indices(self, names):
        names = tuple(names)
        if len(set(names)) != len(names):
            raise ValueError("Duplicate attribute demand")
        index = {name: position for position, name in enumerate(self.names)}
        if any(name not in index for name in names):
            raise ValueError("Unknown attribute demand")
        return {name: index[name] for name in names}

    def concatenate(self, other):
        """Preserve input order and every occurrence, including duplicate ids."""
        if self.names != other.names:
            raise ValueError("Concatenation requires a shared schema")
        return PointView(self.names, self._blocks + other._blocks)

    def select(self, inputs, predicate):
        """Filter against the current dense Index and the declared attributes."""
        indices = tuple(self._column_indices(inputs).values())
        output = []
        rank = 0
        for block in self._blocks:
            selected = 0
            for slot in slots(block.mask):
                arguments = (block.columns[index][slot] for index in indices)
                if predicate(rank, *arguments):
                    selected |= 1 << slot
                rank += 1
            if selected:
                output.append(block if selected == block.mask else _Block(block.columns, selected))
        return PointView(self.names, tuple(output))

    def derive(self, name, inputs, evaluate):
        """Write one value per live row using the input view's attributes."""
        if not isinstance(name, str) or not name:
            raise ValueError("Derived attributes require a name")
        indices = tuple(self._column_indices(inputs).values())
        destination = self.names.index(name) if name in self.names else len(self.names)
        names = self.names if destination < len(self.names) else self.names + (name,)
        output = []
        rank = 0
        for block in self._blocks:
            values = [None] * block.length
            for slot in slots(block.mask):
                arguments = (block.columns[index][slot] for index in indices)
                values[slot] = evaluate(rank, *arguments)
                rank += 1
            columns = block.columns[:destination] + (tuple(values),) + block.columns[destination + 1:]
            output.append(_Block(columns, block.mask))
        return PointView(names, tuple(output))

    def observe(self, names, start=0, stop=None):
        """Gather only requested attributes and logical rows in [start, stop)."""
        indices = self._column_indices(names)
        size = len(self)
        stop = size if stop is None else stop
        if not 0 <= start <= stop <= size:
            raise ValueError("Observation lies outside the view")
        result = {name: [] for name in indices}
        if start == stop or not indices:
            return {name: () for name in indices}
        block_index = bisect_right(self._ends, start)
        previous = self._ends[block_index - 1] if block_index else 0
        while previous < stop:
            block = self._blocks[block_index]
            first = max(0, start - previous)
            last = min(stop - previous, block.mask.bit_count())
            visible = tuple(slots(block.mask))[first:last]
            for name, index in indices.items():
                result[name].extend(block.columns[index][slot] for slot in visible)
            previous = self._ends[block_index]
            block_index += 1
        return {name: tuple(values) for name, values in result.items()}

    def rebalance(self, block_rows=MAX_BLOCK_ROWS):
        """Repack once at a chosen boundary and invalidate no earlier view."""
        return self.from_columns(self.observe(self.names), block_rows)
