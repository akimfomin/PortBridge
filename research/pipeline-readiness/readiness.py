"""Replay admission policies for an exact set of first-frame pipeline requests."""

from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush


@dataclass(frozen=True)
class Pipeline:
    key: str
    compile_us: int
    estimated_mib: int
    fails: bool = False


@dataclass(frozen=True)
class Request:
    at_us: int
    key: str
    required: bool = False


@dataclass(frozen=True)
class Limits:
    workers: int
    estimated_mib: int
    protected_workers: int = 0
    protected_mib: int = 0
    protect_from_us: int = 0


@dataclass(frozen=True)
class Compilation:
    key: str
    start_us: int
    finish_us: int
    required_at_start: bool


@dataclass(frozen=True)
class Replay:
    first_frame_ready_us: int | None
    required_wait_us: tuple[int, ...]
    all_completed_us: int
    failed_keys: tuple[str, ...]
    peak_estimated_mib: int
    peak_workers: int
    compilations: tuple[Compilation, ...]


def replay(pipelines, requests, limits):
    """Return pipeline-ready timestamps under fixed compile costs and estimates.

    The input gives one full pipeline identity per key and all first-frame uses.
    A backend has to provide equivalent keys and a real first-frame-ready signal.
    """
    limit_values = (limits.workers, limits.estimated_mib, limits.protect_from_us,
                    limits.protected_workers, limits.protected_mib)
    if (any(type(value) is not int for value in limit_values)
            or limits.workers < 1 or limits.estimated_mib < 1 or limits.protect_from_us < 0
            or not 0 <= limits.protected_workers <= limits.workers
            or not 0 <= limits.protected_mib <= limits.estimated_mib):
        raise ValueError("Invalid admission limits")
    pipelines = tuple(pipelines)
    if any(
        type(p.key) is not str or not p.key
        or type(p.compile_us) is not int or p.compile_us <= 0
        or type(p.estimated_mib) is not int or not 0 < p.estimated_mib <= limits.estimated_mib
        or type(p.fails) is not bool
        for p in pipelines
    ):
        raise ValueError("Expected compilable jobs within the memory budget")
    work = {pipeline.key: pipeline for pipeline in pipelines}
    if len(work) != len(pipelines):
        raise ValueError("Expected distinct full keys")
    arrivals = defaultdict(list)
    required = []
    for request in requests:
        if (type(request.at_us) is not int or request.at_us < 0
                or type(request.key) is not str or request.key not in work
                or type(request.required) is not bool):
            raise ValueError("Invalid request time or pipeline identity")
        arrivals[request.at_us].append(request)
        if request.required:
            required.append(request)
    if not required:
        raise ValueError("At least one first-frame requirement is needed")
    required.sort(key=lambda request: request.at_us)

    timestamps = iter(sorted(arrivals))
    arrival = next(timestamps, None)
    active = []
    pending = {}
    running = set()
    completed = {}
    failed = set()
    required_keys = set()
    compilations = []
    frame_ready = None
    frame_failed = False
    active_mib = background_mib = background_workers = 0
    peak_mib = peak_workers = 0
    seen_required = 0
    now = 0

    while arrival is not None or active or pending:
        while active and active[0][0] == now:
            finished, _, key, was_required = heappop(active)
            charge = work[key].estimated_mib
            active_mib -= charge
            if not was_required:
                background_mib -= charge
                background_workers -= 1
            running.remove(key)
            completed[key] = finished
            if work[key].fails:
                failed.add(key)

        if now == arrival:
            for request in arrivals[now]:
                seen_required += request.required
                key = request.key
                if request.required:
                    required_keys.add(key)
                if key in completed or key in running:
                    continue
                if request.required and pending.get(key) is False:
                    del pending[key]
                pending[key] = pending.get(key, False) or request.required
            arrival = next(timestamps, None)
        frame_failed = not failed.isdisjoint(required_keys)
        if (not frame_failed and frame_ready is None and seen_required == len(required)
                and required_keys.issubset(completed)):
            frame_ready = now

        protected = not frame_failed and frame_ready is None and now >= limits.protect_from_us
        while pending and len(active) < limits.workers:
            free_mib = limits.estimated_mib - active_mib
            demand = next((key for key, is_required in pending.items() if is_required), None)
            if demand is not None:
                # Wait instead of consuming more capacity while the first required job is blocked.
                if work[demand].estimated_mib > free_mib:
                    break
                key = demand
            else:
                if protected and background_workers >= limits.workers - limits.protected_workers:
                    break
                allowance = limits.estimated_mib - limits.protected_mib - background_mib
                if protected:
                    free_mib = min(free_mib, allowance)
                key = next((key for key in pending if work[key].estimated_mib <= free_mib), None)
                if key is None:
                    break
            was_required = pending.pop(key)
            pipeline = work[key]
            finish = now + pipeline.compile_us
            heappush(active, (finish, len(compilations), key, was_required))
            running.add(key)
            compilations.append(Compilation(key, now, finish, was_required))
            active_mib += pipeline.estimated_mib
            if not was_required:
                background_mib += pipeline.estimated_mib
                background_workers += 1
            peak_mib = max(peak_mib, active_mib)
            peak_workers = max(peak_workers, len(active))

        future = [at for at in (arrival, active[0][0] if active else None) if at is not None]
        if not future:
            if pending:
                raise RuntimeError("Pending pipelines cannot make progress")
            break
        now = min(future)

    waits = tuple(max(0, completed[request.key] - request.at_us) for request in required)
    return Replay(frame_ready, waits, max(completed.values()), tuple(sorted(failed)),
                  peak_mib, peak_workers, tuple(compilations))
