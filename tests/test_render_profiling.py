from unittest.mock import patch

from render_profiling import record_timing


def test_disabled_timer_does_not_sample_clock():
    with patch('render_profiling.perf_counter') as clock:
        record_timing(None, 'draw', 1)
        clock.assert_not_called()


def test_timer_aggregates_without_retaining_frames():
    timings = {}
    with patch('render_profiling.perf_counter', side_effect=[2.0, 4.0]):
        record_timing(timings, 'draw', 1.0)
        record_timing(timings, 'draw', 2.0)
    assert timings['draw'] == {
        'count': 2, 'total_s': 3.0, 'min_s': 1.0, 'max_s': 2.0, 'first_s': 1.0,
    }
