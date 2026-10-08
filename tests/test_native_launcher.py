import os
from pathlib import Path
import subprocess


def test_wrapper_environment_paths_and_no_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ego, mint = tmp_path / 'ego space', tmp_path / 'mint space'
    for folder in (ego / 'scripts', mint / 'scripts', tmp_path / 'depth'):
        folder.mkdir(parents=True)
    (ego / 'run.py').touch()
    local = ego / 'scripts/export_egohandkit_cache_mint.py'
    local.write_text('fixture exporter')
    video, prediction = tmp_path / 'video.mp4', tmp_path / 'prediction.npz'
    video.touch()
    prediction.touch()
    python = tmp_path / 'fake python'
    python.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n'
                      'while [[ $# -gt 0 ]]; do\n'
                      'if [[ "$1" == --out ]]; then printf artifact > "$2"; break; fi\n'
                      'shift\ndone\n')
    python.chmod(0o755)
    log = tmp_path / 'calls'
    env = dict(os.environ, EGOHANDKIT_ROOT=str(ego), MINT_ROOT=str(mint),
               EGOHANDKIT_PYTHON=str(python), CALL_LOG=str(log))
    command = ['bash', str(root / 'scripts/run_without_front.sh'), 'mint', str(video),
               str(prediction), str(tmp_path / 'depth'), str(tmp_path / 'output')]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert len(calls) == 2
    assert '--wrist_surface_depth_compensation' in calls[1]
    assert '--orientation_bucket_gate' in calls[1]
    exporter = mint / 'scripts/export_egohandkit_cache.py'
    assert exporter.read_bytes() == local.read_bytes()
    exporter.write_text('existing edits')
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'reconcile explicitly' in result.stderr
    assert exporter.read_text() == 'existing edits'
    assert len(log.read_text().splitlines()) == 2
