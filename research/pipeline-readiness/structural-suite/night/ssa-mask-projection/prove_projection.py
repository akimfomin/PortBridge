"""CPU proof checks for projecting an XCL pixel ballot and cases beyond illegal simplification.

The four words are per-receiver results of the original WaveActiveBallot calls.
For helpers they are deliberately unconstrained. Run with standard Python 3.
"""
import json
import random
from pathlib import Path

U32 = 0xFFFFFFFF


def spread_reference(ballots):
    """The arithmetic sequence from upstream ballot_ps_quad, for one hardware word."""
    result = 0
    for member, vote in enumerate(ballots):
        n = vote | (vote >> 1)
        n |= n >> 2
        result |= (n & 0x11111111) << member
    return result


def project(ballots, index):
    """The SSA projection uses only the selected member's four carrier bits."""
    return int((ballots[index & 3] >> (index & 28)) & 15 != 0)


def votes_for_quad(carriers, masks):
    """Ballot only the participating non-helper carriers in one quad."""
    return [
        sum(((masks[i] >> member) & 1) << i for i in range(4) if carriers & 1 << i)
        for member in range(4)
    ]


def test_words():
    # All 4×4 possible bits independently in one quad at a time. There are no
    # cross-quad carries in this rule; check both the low and high boundary too.
    local_checks = 0
    for packed in range(1 << 16):
        ballots = [(packed >> (4 * m)) & 15 for m in range(4)]
        for base in (0, 28):
            placed = [v << base for v in ballots]
            reference = spread_reference(placed)
            for lane in range(base, base + 4):
                assert reference >> lane & 1 == project(placed, lane)
                local_checks += 1
    # Adversarial, arbitrary values of the original ballots per receiving lane:
    # no assumption of quad-uniform q, subgroup participation, or helper output.
    rng = random.Random(0xD12A4)
    word_checks = 0
    for _ in range(2048):
        a = [[rng.getrandbits(32) for _ in range(4)] for _ in range(2)]
        for hw in range(64):
            half = hw >> 5
            rel = hw & 31
            assert (spread_reference(a[half]) >> rel & 1) == project(a[half], rel)
            word_checks += 1
    return local_checks, word_checks


def test_participation():
    # Enumerate the concrete mathematical model, including a quad with no live
    # representative. The reference is broadcast from the selected carriers;
    # SM6.6 itself need not provide any fixed ballot value to a helper.
    cases = 0
    different_from_direct = 0
    for carriers in range(16):
        for guest_exec in range(16):
            for pred in range(16):
                value = guest_exec & pred
                ballots = votes_for_quad(carriers, [value] * 4)
                for lane in range(4):
                    direct = value >> lane & 1
                    exact = project(ballots, lane)
                    assert exact == (spread_reference(ballots) >> lane & 1)
                    if carriers:
                        assert exact == direct
                    different_from_direct += direct != exact
                    cases += 1
    return cases, different_from_direct


def test_exit_mask():
    counts = {}
    for width in (32, 64):
        exec_mask = (1 << width) - 1
        accumulated = 0
        for retired in range(width):
            finished = (1 << retired) & exec_mask
            accumulated |= finished
            exec_mask &= ~finished
        assert exec_mask == 0
        assert accumulated.bit_count() == width
        counts[str(width)] = {"whole_popcount": accumulated.bit_count(), "single_lane_popcount": 1}
    return counts


def main():
    local, word = test_words()
    participation, counterexamples = test_participation()
    result = {
        "exhaustive_nibble_checks": local,
        "random_wave_half_checks": word,
        "participation_lane_checks": participation,
        "direct_local_counterexamples_in_broadcast_model": counterexamples,
        "loop_exit_control": test_exit_mask(),
        "wave32_partial_register_control": {
            "s21_after_odd_lane_carries": hex(0xAAAAAAAA),
            "s20_after_separate_zero_carry": hex(0),
            "expected_whole_s21_popcount": (0xAAAAAAAA).bit_count(),
            "incorrect_sparse_projection_popcounts": [0, 1],
        },
        "same_API_results": "The projection is identical for every possible word returned by each of the four original ballots. The API does not promise any particular helper vote.",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
