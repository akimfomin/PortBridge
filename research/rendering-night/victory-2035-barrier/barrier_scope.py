"""Source-filtered static review of #2035. No shader, GPU work, or binary."""

import argparse
from collections import namedtuple
from pathlib import Path
import subprocess


PIN = "5b347035f16b4361fc483a4abd42ffffddca9188"
LOWER = "crates/victory-shader/src/emit/lower.rs"
GROUP_SYNC = 1
UAV_GLOBAL_FENCE = 2
TGSM_FENCE = 8
Exit = namedtuple("Exit", "targets atoms", defaults=((), ()))


def source_check(repo):
    source = subprocess.check_output(["git", "show", f"{PIN}:{LOWER}"], cwd=repo,
                                     text=True, encoding="utf-8")
    nodes = source[source.index("fn lane_exit_loop_blocks("):source.index("fn unsupported(")]
    selector = source[source.index("fn barrier_unsynced("):source.index("    /// The console wave size.")]
    flat_start = source.index("fn flat_write(")
    flat_store = source[flat_start:source.index("    fn find_sections(", flat_start)]
    for fragment, expected in (
        (nodes, ("1 => back.push((b, t))", "loops.entry(head).or_default().push(tail)",
                 "exits_loop(b) && lane_branch(b)", "out.extend(body)",
                 "if host_wave_max >= console_wave", "group_threads.is_some_and(|t| t <= console_wave)",
                 "in_lane_exit_loop || non_uniform_reach")),
        (selector, ("let group_threads = self.s.threads.map(|t| t.iter().product());",
                    "self.lane_loops.contains(&b)", ".support(st.reach[b])", "Atom::Uniform(_)")),
        (source, ("matches!(i.fields, Fields::Image { .. } | Fields::Buffer { .. })",
                  'i.name().contains("store") || i.name().contains("atomic")',
                  "if self.barrier_unsynced(b) { mode & !1 } else { mode }",
                  "if console_lanes || one_wave && s.lds_dwords > 0")),
        (flat_store, ("let Fields::Flat {", 'if name.starts_with("global_store_")',
                      '"rawBufferStore.i32"', "mark_view_write")),
    ):
        assert all(line in fragment for line in expected), "pinned source fragments changed"


def lane_loops(exits):
    """Transcription of lane_exit_loop_blocks for the resolved finite graphs below."""
    predecessor = [[] for _ in exits]
    for node, exit in enumerate(exits):
        for target in exit.targets:
            predecessor[target].append(node)

    stack = [(0, 0)]
    state = [1, *([0] * (len(exits) - 1))]
    back_edges = []
    while stack:
        node, next_index = stack[-1]
        targets = exits[node].targets
        if next_index == len(targets):
            state[node] = 2
            stack.pop()
            continue
        target = targets[next_index]
        stack[-1] = (node, next_index + 1)
        if state[target] == 0:
            state[target] = 1
            stack.append((target, 0))
        elif state[target] == 1:
            back_edges.append((node, target))

    marked = set()
    tails_by_head = {}
    for tail, head in back_edges:
        tails_by_head.setdefault(head, []).append(tail)
    for head, tails in tails_by_head.items():
        body = {head}
        work = list(tails)
        while work:
            node = work.pop()
            if node not in body:
                body.add(node)
                work.extend(predecessor[node])
        if any(any(target not in body for target in exits[node].targets)
               and any(atom != "uniform" for atom in exits[node].atoms)
               for node in body):
            marked.update(body)
    return marked


def wip_mode(exits, barrier, reach_atoms, host_max, console_wave, group_threads, writes_uavs=False):
    mode = GROUP_SYNC | TGSM_FENCE | (UAV_GLOBAL_FENCE if writes_uavs else 0)
    divergent = barrier in lane_loops(exits) or any(atom != "uniform" for atom in reach_atoms)
    one_console_wave = group_threads is not None and group_threads <= console_wave
    if host_max < console_wave and one_console_wave and divergent:
        return mode & ~GROUP_SYNC
    return mode


def eligible_action(group_arrival_proven, independence_proven):
    # Unknown is not proof. This fixture supplies the two proofs as inputs;
    # it does not infer them from arbitrary shaders or the branch labels above.
    if group_arrival_proven:
        return "keep group sync"
    if independence_proven:
        return "fence only"
    return "require reconvergence or refuse"


def orders(left, right):
    if not left or not right:
        yield left + right
        return
    for suffix in orders(left[1:], right):
        yield left[:1] + suffix
    for suffix in orders(left, right[1:]):
        yield right[:1] + suffix


def outcomes(group_sync):
    observed = set()
    for sequence in orders(("write", "arrive_A"), ("arrive_B", "read")):
        if group_sync and sequence.index("read") < sequence.index("arrive_A"):
            continue
        observed.add(int(sequence.index("write") < sequence.index("read")))
    return observed


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--repo", type=Path, default=Path.cwd())
    repo = args.parse_args().repo
    source_check(repo)

    # Uniform header: 1 -> 2 (body) or 6 (leave). The lane-dependent 2 -> 3/4
    # reconverges at the only barrier, 5. Both arms reach 5 exactly once;
    # the group-uniform header is the only choice of another iteration.
    diamond = [Exit((1,)), Exit((2, 6), ("uniform",)), Exit((3, 4), ("lane",)),
               Exit((5,)), Exit((5,)), Exit((1,)), Exit()]
    assert lane_loops(diamond) == set()
    for group_threads in (64, 128):
        assert wip_mode(diamond, 5, ("uniform",), 32, 64, group_threads) == GROUP_SYNC | TGSM_FENCE
    assert eligible_action(True, False) == "keep group sync"
    print("uniform-trip diamond: revised #2035 corrects earlier result and keeps group sync")

    # A real per-lane exit from the loop can change dynamic visit counts.
    divergent_exit = [Exit((1,)), Exit((2, 3), ("lane",)), Exit((1,)), Exit()]
    assert lane_loops(divergent_exit) == {1, 2}
    assert wip_mode(divergent_exit, 2, ("lane",), 32, 64, 128) == GROUP_SYNC | TGSM_FENCE
    assert wip_mode(divergent_exit, 2, ("lane",), 32, 64, 64) == TGSM_FENCE
    assert wip_mode(divergent_exit, 2, ("lane",), 32, 64, None) == GROUP_SYNC | TGSM_FENCE
    assert eligible_action(False, False) == "require reconvergence or refuse"
    assert eligible_action(False, True) == "fence only"
    print("nonuniform exit: revised #2035 strips only for known single-console-wave group on this host")

    # First loop epoch known to reach the site in both halves of the guest wave.
    # Later epochs may take the nonuniform exit, causing the same static site to
    # be marked. A compute shader with zero LDS need not pin the guest wave size.
    # Give the generated shader a real UAV fence and still model a racing read.
    correct_uav_fences = wip_mode(divergent_exit, 2, ("lane",), 32, 64, 64, True)
    assert correct_uav_fences == TGSM_FENCE | UAV_GLOBAL_FENCE
    assert outcomes(bool(correct_uav_fences & GROUP_SYNC)) == {0, 1}
    assert outcomes(True) == {1}
    print("one guest wave, two host waves: mode 11 -> 10 at the marked site")
    print("first-epoch static orders: required handoff gives read=1; fence-only admits read=0 and read=1")

    # A console device write can be a Fields::Flat 'global_store_dword'.
    # The exact pre-existing writes_uavs predicate ignores that path.
    flat_store = ("Flat", "global_store_dword")
    writes_uavs = flat_store[0] in ("Image", "Buffer") and ("store" in flat_store[1] or "atomic" in flat_store[1])
    assert not writes_uavs
    assert wip_mode(divergent_exit, 2, ("lane",), 32, 64, 64, writes_uavs) == TGSM_FENCE
    print("flat UAV write: exact predicate is false even though the lowerer emits rawBufferStore; zero LDS is insufficient")

    print("scope: pinned source and synthetic control/event model; no translator or GPU executed")


if __name__ == "__main__":
    main()
