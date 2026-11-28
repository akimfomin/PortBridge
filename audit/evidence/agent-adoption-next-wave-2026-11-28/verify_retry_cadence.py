"""CPU model for periodic receipt writes with a failing output sink."""
BATCH = 64


def exercise(total, *, old, allowed, imported=0, try_early=False):
    pending = since_attempt = imported
    attempts = 0
    for _ in range(total):
        pending += 1
        since_attempt += 1
        if (pending if old else since_attempt) >= BATCH:
            attempts += 1
            since_attempt = 0
            if allowed:
                pending = 0
    # A final save must be allowed independently of the periodic threshold.
    recovered = pending if try_early else 0
    if try_early and pending:
        attempts += 1
        pending = 0
    return attempts, pending, recovered


if __name__ == "__main__":
    assert exercise(1024, old=True, allowed=False) == (961, 1024, 0)
    assert exercise(1024, old=False, allowed=False) == (16, 1024, 0)
    assert exercise(1024, old=False, allowed=True) == (16, 0, 0)
    assert exercise(1024, old=False, allowed=False, try_early=True) == (17, 0, 1024)
    assert exercise(65, old=False, allowed=False, try_early=True) == (2, 0, 65)
    assert exercise(1, old=False, allowed=True, imported=64) == (1, 0, 0)
    print("1,024 new keys: 961 -> 16 failed periodic write attempts.")
    print("Successful writer: 16 attempts. Forced final save preserved all 1,024 after recovery.")
