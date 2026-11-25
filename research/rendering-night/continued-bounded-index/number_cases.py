"""Generate the numeric acceptance and binary64 differential fixture."""

import random


def tokens():
    for integer in range(1 << 16):
        yield str(integer)
    for extent in range(1, 324):
        yield "9" * extent
        yield "0" * extent + "1"
    yield from (
        "", " ", "0", "-0", "+0", "0.0", "0e-8", "1e999", "1e-999", "1e", "1e+",
        "-9007199254740992", "9007199254740992", "9007199254740993", "-.6", "6.",
        "0E+0000001", "-000", "15\0", "15abc", "15 " + "2", "true", "+", "-", ".",
        '{"n": 3}', '[0, 1, 999999999999999]', "01234", "1.0000000000000002",
    )
    rng = random.Random(40318)
    for _ in range(45_000):
        size = rng.randrange(1, 34)
        base = "".join(str(rng.randrange(10)) for _ in range(size))
        choices = (
            base, "+" + base, "-" + base, base + "." + base,
            base + "e-" + str(rng.randrange(340)), base + "x" + base,
        )
        yield rng.choice(choices)
