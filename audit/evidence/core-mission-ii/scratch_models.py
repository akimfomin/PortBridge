"""Compare two width-1/2 slot-placement rules on inclusive synthetic intervals."""
import json
from random import Random
from statistics import median


def place(values, prefer_long, use_free_tail):
    # A value is given as (definition stage, final carrying stage, word count).
    order = sorted(range(len(values)), key=lambda i: (values[i][0], -values[i][1] if prefer_long else 0, i))
    layout = {}
    capacity = 0
    for i in order:
        first, _, width = values[i]
        used = {word for j, start in layout.items() if values[j][1] >= first
                for word in range(start, start + values[j][2])}
        stop = capacity if use_free_tail else max(0, capacity + 1 - width)
        free = next((pos for pos in range(stop) if used.isdisjoint(range(pos, pos + width))), capacity)
        capacity = max(capacity, free + width)
        layout[i] = free
    for i, (first, last, width) in enumerate(values):
        for j in range(i):
            begin, end, size = values[j]
            if first <= end and begin <= last:
                assert layout[i] + width <= layout[j] or layout[j] + size <= layout[i], (i, j)
    return capacity + 1  # Together with the continuation tag.


def main():
    rng = Random(2322)
    records, examples = [], {}
    for _ in range(10_000):
        values = []
        for _ in range(rng.randint(5, 70)):
            first = rng.randrange(18)
            values.append((first, rng.randint(first + 1, 18), rng.choice((1, 1, 1, 2))))
        upstream = place(values, False, False)
        draft = place(values, True, True)
        static = 1 + sum(value[2] for value in values)
        lower = 1 + max(sum(width for first, last, width in values if first <= stage <= last)
                        for stage in range(19))
        assert lower <= min(upstream, draft) <= max(upstream, draft) <= static
        records.append((upstream, draft))
        if upstream != draft:
            direction = "draft_smaller" if draft < upstream else "upstream_smaller"
            if direction not in examples or len(values) < len(examples[direction]["intervals"]):
                examples[direction] = {"intervals": values, "draft": draft, "upstream": upstream, "lower": lower}
    print(json.dumps({"cases": len(records), "seed": 2322, "draft_smaller": sum(d < u for u, d in records),
                      "equal": sum(u == d for u, d in records), "upstream_smaller": sum(u < d for u, d in records),
                      "median_draft_minus_upstream_words": median([d - u for u, d in records]),
                      "smallest_observed_examples": examples}, indent=2))


if __name__ == "__main__":
    main()
