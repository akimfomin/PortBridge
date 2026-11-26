"""Independent CPU oracle for XCL's four ballot/quad spreads and packed OR.

Run with Python 3.10+. Only live, defined wave-operation results are comparable.
A None in an executing contributor represents an undefined q. This model then
makes no claim about the result. A non-participating lane does not contribute.
"""

import argparse
import itertools
import json
import random


def four_ballots(values, contributors):
    """Translate XCL's literal four ballots and word-local shift/spread steps."""
    if any(values[lane] is None for lane in contributors):
        return None
    words = [0, 0]
    for bit in range(4):
        ballot = sum(1 << lane for lane in contributors if values[lane] & (1 << bit))
        for word in range(2):
            votes = (ballot >> (32 * word)) & 0xFFFFFFFF
            votes |= votes >> 1
            votes |= votes >> 2
            words[word] |= (votes & 0x11111111) << bit
    return tuple(words)


def packed_or(values, contributors):
    """Each physical lane selects one word and deposits its entire nibble."""
    if any(values[lane] is None for lane in contributors):
        return None
    words = [0, 0]
    for lane in contributors:
        word = lane // 32
        if word < 2:
            words[word] |= (values[lane] & 15) << (lane & 28)
    return tuple(words)


def check(values, contributors):
    reference = four_ballots(values, contributors)
    candidate = packed_or(values, contributors)
    if candidate != reference:
        raise AssertionError((values, contributors, reference, candidate))
    return candidate


def exhaustive_quad():
    distinct = 0
    total = 0
    # 16 possible nibbles and absence. A non-contributor's q is unobserved.
    for values in itertools.product([None, *range(16)], repeat=4):
        contributors = [i for i, v in enumerate(values) if v is not None]
        check(values, contributors)
        distinct += len({values[i] for i in contributors}) > 1
        total += 1
    return {"quad_states": total, "states_with_different_contributors_q": distinct}


def word_boundaries():
    cases = 0
    # A single set bit per physical lane is a basis for independent OR terms.
    for width in (4, 8, 16, 32, 64, 128):
        for contributor in range(width):
            for nibble_bit in range(4):
                values = [None] * width
                values[contributor] = 1 << nibble_bit
                got = check(values, [contributor])
                expected = (1 << ((contributor // 4) * 4 + nibble_bit)) & ((1 << 64) - 1)
                if got != (expected & 0xFFFFFFFF, expected >> 32):
                    raise AssertionError((contributor, nibble_bit, expected, got))
                cases += 1
    return cases


def wave_observation(result, lane, executing, helpers, include_helpers):
    if lane not in executing or (lane in helpers and not include_helpers):
        return None
    return result


def random_waves(seed, repetitions):
    rng = random.Random(seed)
    populations = []
    for width in (4, 8, 16, 32, 64, 128):
        counts = {"calls": 0, "defined_observers": 0, "undefined_observers": 0}
        for _ in range(repetitions):
            # Independent control-flow participation and pixel helper classification.
            executing = {i for i in range(width) if rng.randrange(3)}
            helpers = {i for i in range(width) if rng.randrange(3) == 0}
            values = [rng.getrandbits(32) for _ in range(width)]
            for include_helpers in (False, True):
                participants = executing if include_helpers else executing - helpers
                reference = four_ballots(values, participants)
                candidate = packed_or(values, participants)
                if candidate != reference:
                    raise AssertionError((width, participants, reference, candidate))
                counts["calls"] += 1
                for lane in range(width):
                    observed = wave_observation(candidate, lane, executing, helpers, include_helpers)
                    if observed is None:
                        counts["undefined_observers"] += 1
                    else:
                        if observed != reference:
                            raise AssertionError((lane, reference, observed))
                        counts["defined_observers"] += 1
        populations.append({"host_width": width, **counts})
    return populations


def incorrect_packing(values, contributors, rule):
    """Deliberately wrong alternatives; each has a small failing witness."""
    words = [0, 0]
    represented = set()
    for lane in contributors:
        word = lane // 32
        if rule == "host128_low_alias":
            word %= 2
        elif rule == "host128_high_alias":
            word = min(word, 1)
        if word >= 2 or (rule == "representative_only" and lane // 4 in represented):
            continue
        represented.add(lane // 4)
        bits = values[lane] if rule == "unmasked_q" else values[lane] & 15
        words[word] |= (bits << (lane & 28)) & 0xFFFFFFFF
    return tuple(words)


def negative_controls():
    # Explicit counterexamples for related, tempting rewrites.
    values = [0] * 128
    values[64] = 9
    result = check(values, [64])
    assert result == (0, 0)
    assert result != incorrect_packing(values, [64], "host128_low_alias")
    assert result != incorrect_packing(values, [64], "host128_high_alias")

    values = [0x11, 0x22, 0x44, 0x88]
    result = check(values, range(4))
    assert result == (15, 0)
    assert result != incorrect_packing(values, range(4), "representative_only")
    assert result != incorrect_packing(values, range(4), "unmasked_q")

    values = [8, 2, 0, 0, 1, 2, 4, 8]
    assert check(values, [1]) == (2, 0)  # An absent representative may not contribute.
    assert check(values, [0, 1, 2, 3]) == (10, 0)  # Entire other quad inactive.
    assert check(values, []) == (0, 0)  # Internal reduction only. No observable lane.
    assert wave_observation((2, 0), 0, {0, 1}, {0}, False) is None
    assert wave_observation((10, 0), 0, {0, 1}, {0}, True) == (10, 0)
    assert check([None, 2, 0, 0], [0, 1]) is None  # Unknown live q is outside proof.
    assert check([None, 2, 0, 0], [1]) == (2, 0)
    return ["host128_low_alias", "host128_high_alias", "representative_only",
            "unmasked_q", "inactive_quad", "default_helper_consumer",
            "included_helper_consumer", "undefined_live_input"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261126)
    parser.add_argument("--repetitions", type=int, default=1024)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    print(json.dumps({
        "seed": args.seed,
        "scope": "defined active contributors within one dynamic wave operation",
        "exhaustive": exhaustive_quad(),
        "individual_lane_bit_basis": word_boundaries(),
        "waves": random_waves(args.seed, args.repetitions),
        "negative_controls": negative_controls(),
    }, indent=2))


if __name__ == "__main__":
    main()
