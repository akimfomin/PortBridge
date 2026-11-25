# SPDX-License-Identifier: MIT
"""Bounded translation validation for a single indexed or XOR subgroup read."""

from dataclasses import asdict, dataclass
from enum import StrEnum
from itertools import product
from typing import Iterable


class Addressing(StrEnum):
    INDEX = "index"
    XOR = "xor"


class Inactive(StrEnum):
    ZERO = "zero"
    UNDEFINED = "undefined"


class LaneBase(StrEnum):
    PARTITION = "destination-partition"
    HOST = "physical-subgroup"


class Participation(StrEnum):
    FULL = "full"
    EXEC = "exec"
    SUPERSET = "superset"
    INDEPENDENT = "independent"


class Exchange(StrEnum):
    NONE = "none"
    CURRENT = "current"
    STALE = "stale"


class Value(StrEnum):
    OLD = "destination"
    ZERO = "zero"
    UNDEFINED = "undefined"
    CURRENT = "source"
    STALE = "prior-epoch"


@dataclass(frozen=True)
class Guest:
    scope: int
    addressing: Addressing = Addressing.INDEX
    inactive_source: Inactive = Inactive.ZERO


@dataclass(frozen=True)
class Lowering:
    scope: int
    addressing: Addressing = Addressing.INDEX
    guest_guard: bool = True
    host_guard: bool = False
    preserve_inactive: bool = True
    exchange: Exchange = Exchange.NONE
    lane_base: LaneBase = LaneBase.PARTITION


@dataclass(frozen=True)
class Domain:
    wave: int
    physical: int
    participation: Participation


@dataclass(frozen=True)
class Probe:
    destination: int
    selector: int
    exec_mask: int
    host_mask: int


@dataclass(frozen=True)
class Mismatch:
    probe: Probe
    expected: tuple[Value, int]
    actual: tuple[Value, int]
    reason: str

    def record(self) -> dict:
        return {
            "destination": self.probe.destination,
            "selector": self.probe.selector,
            "exec": hex(self.probe.exec_mask),
            "host": hex(self.probe.host_mask),
            "expected": self.expected,
            "actual": self.actual,
            "reason": self.reason,
        }


def validate(guest: Guest, lower: Lowering, domain: Domain) -> None:
    for width in (domain.wave, domain.physical, guest.scope, lower.scope):
        if width <= 0 or width > domain.wave or width & (width - 1):
            raise ValueError("positive power-of-two lane widths must fit in the guest wave")
    if domain.wave > 64:
        raise ValueError("at most 64 guest lanes are supported")
    if lower.lane_base == LaneBase.HOST and lower.scope > domain.physical:
        raise ValueError("host-relative selectors must fit the physical subgroup")


def source(scope: int, addressing: Addressing, lane: int, selector: int) -> int:
    local = selector if addressing == Addressing.INDEX else lane ^ selector
    return (lane & ~(scope - 1)) | (local & (scope - 1))


def target_source(lower: Lowering, domain: Domain, lane: int, selector: int) -> int:
    if lower.lane_base == LaneBase.PARTITION:
        return source(lower.scope, lower.addressing, lane, selector)
    local = selector if lower.addressing == Addressing.INDEX else lane ^ selector
    return (lane & ~(domain.physical - 1)) | (local & (lower.scope - 1))


def active(mask: int, lane: int) -> bool:
    return bool(mask & (1 << lane))


def compare(guest: Guest, lower: Lowering, domain: Domain, p: Probe) -> Mismatch | None:
    """Compare abstract tokens. Different input-lane symbols can differ."""
    lane = p.destination
    if not active(p.exec_mask, lane):
        expected = (Value.OLD, lane)
    else:
        origin = source(guest.scope, guest.addressing, lane, p.selector)
        if active(p.exec_mask, origin):
            expected = (Value.CURRENT, origin)
        else:
            expected = (Value(guest.inactive_source), -1)

    selected = target_source(lower, domain, lane, p.selector)
    if not active(p.host_mask, lane):
        actual = (Value.OLD, lane)
    elif not active(p.exec_mask, lane) and lower.preserve_inactive:
        actual = (Value.OLD, lane)
    elif lower.guest_guard and not active(p.exec_mask, selected):
        actual = (Value.ZERO, -1)
    elif selected // domain.physical == lane // domain.physical and active(p.host_mask, selected):
        actual = (Value.CURRENT, selected)
    elif lower.exchange == Exchange.CURRENT:
        actual = (Value.CURRENT, selected)
    elif lower.exchange == Exchange.STALE:
        actual = (Value.STALE, selected)
    elif lower.host_guard:
        actual = (Value.ZERO, -1)
    else:
        actual = (Value.UNDEFINED, -1)

    if expected[0] == Value.UNDEFINED or expected == actual:
        return None
    if actual[0] == Value.UNDEFINED:
        reason = "target returns undefined for a defined guest result"
    elif actual[0] == Value.STALE:
        reason = "exchange does not represent the current snapshot"
    elif expected[0] == actual[0] == Value.CURRENT:
        reason = "target reads a different source lane"
    else:
        reason = "target changes a defined guest value"
    return Mismatch(p, expected, actual, reason)


def project(guest: Guest, lower: Lowering, domain: Domain, lane: int, selector: int) -> Iterable[Probe]:
    """Represent each mask equivalence class for one destination/selector pair."""
    origin = source(guest.scope, guest.addressing, lane, selector)
    selected = target_source(lower, domain, lane, selector)
    guest_bits = sorted({lane, origin, selected})
    for bits in product((0, 1), repeat=len(guest_bits)):
        mask = sum(bit << index for bit, index in zip(bits, guest_bits))
        if domain.participation == Participation.FULL:
            yield Probe(lane, selector, mask, (1 << domain.wave) - 1)
        elif domain.participation == Participation.EXEC:
            yield Probe(lane, selector, mask, mask)
        else:
            host = 1 << lane
            if domain.participation == Participation.SUPERSET:
                host |= mask
            yield Probe(lane, selector, mask, host)
            if not active(host, selected):
                yield Probe(lane, selector, mask, host | (1 << selected))


def check(guest: Guest, lower: Lowering, domain: Domain) -> dict:
    """Enumerate every pair and projected mask class in the declared domain."""
    validate(guest, lower, domain)
    total = failures = 0
    witnesses = {}
    for lane, selector in product(range(domain.wave), repeat=2):
        for probe in project(guest, lower, domain, lane, selector):
            total += 1
            if mismatch := compare(guest, lower, domain, probe):
                failures += 1
                witnesses.setdefault(mismatch.reason, mismatch.record())
    return {
        "status": "refuted" if failures else "passes modeled domain",
        "projected_probes": total,
        "failing_projected_probes": failures,
        "guest": asdict(guest),
        "target": asdict(lower),
        "domain": asdict(domain),
        "witnesses": list(witnesses.values()),
    }
