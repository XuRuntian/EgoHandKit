"""Opt-in wall-time aggregates; no CUDA synchronization or per-frame logging."""

from time import perf_counter


def record_timing(timings, name, started):
    if timings is None:
        return
    elapsed = perf_counter() - started
    item = timings.setdefault(name, {
        'count': 0, 'total_s': 0.0, 'min_s': elapsed,
        'max_s': elapsed, 'first_s': elapsed,
    })
    item['count'] += 1
    item['total_s'] += elapsed
    item['min_s'] = min(item['min_s'], elapsed)
    item['max_s'] = max(item['max_s'], elapsed)
