"""Arithmetic model for the texture-pool review in AnyXboxX #550."""

BLOCK_MIB = 64
MINIMUM = 2
MAXIMUM = 64


def limit(budget, used, keep, empty_blocks):
    if not keep or budget is None or used * 100 >= budget * 85:
        return MINIMUM
    room_in_blocks = (budget * 85 // 100 - used) // BLOCK_MIB
    return min(MAXIMUM, max(MINIMUM, empty_blocks + room_in_blocks))


def trace(budget, used, keep, previous, allow_increase):
    steps = [previous]
    for _ in range(4):
        proposed = limit(budget, used, keep, steps[-1])
        steps.append(proposed if allow_increase else min(steps[-1], proposed))
    return steps


def main():
    cases = {
        "busy_8gb_old": trace(7188, 5822, True, 4, True),
        "busy_8gb_no_increase": trace(7188, 5822, True, 4, False),
        "busy_8gb_over_line": trace(7188, 6200, True, 4, False),
        "busy_8gb_pressure": trace(7188, 5822, False, 4, False),
        "roomy_12gb": limit(12288, 6144, True, 0),
        "near_line_12gb": limit(12288, 9830, True, 0),
    }
    assert cases["busy_8gb_old"] == [4, 8, 12, 16, 20]
    assert cases["busy_8gb_no_increase"] == [4] * 5
    assert cases["busy_8gb_over_line"] == [4, 2, 2, 2, 2]
    assert cases["busy_8gb_pressure"] == [4, 2, 2, 2, 2]
    assert (cases["roomy_12gb"], cases["near_line_12gb"]) == (64, 9)
    print(cases)


if __name__ == "__main__":
    main()
