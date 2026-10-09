import json
import ast
from contextlib import ExitStack
import signal
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from observation_frontend.depth_input import inspect_depth, prepared_depth


@pytest.fixture
def archive(tmp_path):
    if not all(shutil.which(t) for t in ('ffmpeg', 'ffprobe')):
        pytest.skip('FFmpeg tools required')
    root = tmp_path / 'source'
    root.mkdir()
    raw = struct.pack('<6H', 0, 1, 255, 256, 4000, 65535) * 16
    subprocess.run([
        'ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'gray16le',
        '-s', '12x8', '-r', '30', '-i', 'pipe:0', '-c:v', 'ffv1',
        str(root / 'depth_uint16_ffv1.avi'),
    ], input=raw, check=True, capture_output=True)
    spec = dict(enabled=True, codec='ffv1', container='avi', pixel_format='gray16le',
                bit_depth=16, depth_unit='millimeter', invalid_value=0, lossless=True,
                frame_count=1, width=12, height=8)
    meta = dict(stage='depth_archive_v1', unit='millimeter', encoding='uint16',
                invalid_value=0, frame_count=1, frames=[{'frame_idx': 0}], ffv1=spec,
                outputs={'ffv1_video': '/nonexistent/old/machine/path.avi'})
    (root / 'depth_archive_meta.json').write_text(json.dumps(meta))
    (root / 'fast_foundation_stereo_video_meta.json').write_text('{"intrinsics": {}}')
    return root, raw


def test_lossless_and_cleanup(archive, tmp_path):
    root, raw = archive
    output = tmp_path / 'output'
    output.mkdir()
    original = {p.name: p.read_bytes() for p in root.iterdir()}
    with prepared_depth(root, output) as depth:
        restored = subprocess.run([
            'ffmpeg', '-v', 'error', '-i', str(depth / 'depth_uint16_png/frame_000000_depth_mm.png'),
            '-f', 'rawvideo', '-pix_fmt', 'gray16le', 'pipe:1',
        ], capture_output=True, check=True).stdout
        assert restored == raw
        assert (depth / 'fast_foundation_stereo_video_meta.json').read_bytes() == original['fast_foundation_stereo_video_meta.json']
    assert not list(output.iterdir())
    assert original == {p.name: p.read_bytes() for p in root.iterdir()}


def test_cleanup_on_consumer_interrupt(archive, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        with prepared_depth(archive[0], tmp_path) as depth:
            raise KeyboardInterrupt
    assert not depth.exists()


def test_bad_count_cleans_partial_output(archive, tmp_path):
    root, _ = archive
    path = root / 'depth_archive_meta.json'
    meta = json.loads(path.read_text())
    meta['frame_count'] = meta['ffv1']['frame_count'] = 2
    meta['frames'].append({'frame_idx': 1})
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='frame count'):
        with prepared_depth(root, tmp_path):
            pytest.fail('Should not expose partial output')
    assert not list(tmp_path.glob('.hand-depth-*'))


def test_reject_lossy_metadata(archive):
    root, _ = archive
    path = root / 'depth_archive_meta.json'
    meta = json.loads(path.read_text())
    meta['ffv1']['lossless'] = False
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='Unsupported depth archive'):
        inspect_depth(root)


def test_png_passthrough(tmp_path):
    (tmp_path / 'depth_uint16_png').mkdir()
    with prepared_depth(tmp_path, tmp_path / 'unused') as depth:
        assert depth == tmp_path
    assert not (tmp_path / 'unused').exists()


def test_missing_depth_rejected(tmp_path):
    with pytest.raises(ValueError, match='No depth PNG'):
        inspect_depth(tmp_path)


def test_corrupt_archive_not_consumed(archive, tmp_path):
    root, _ = archive
    (root / 'depth_uint16_ffv1.avi').write_bytes(b'broken archive')
    with pytest.raises(subprocess.CalledProcessError):
        with prepared_depth(root, tmp_path):
            pytest.fail('Corrupt archive reached consumer')
    assert not list(tmp_path.glob('.hand-depth-*'))


def test_input_frame_count_mismatch(archive, tmp_path):
    with pytest.raises(ValueError, match='input image frame counts'):
        with prepared_depth(archive[0], tmp_path, expected_frames=2):
            pytest.fail('Mismatched archive reached consumer')
    assert not list(tmp_path.glob('.hand-depth-*'))


@pytest.mark.parametrize('failure', [None, 'error', 'interrupt', 'sigterm'])
def test_entrypoint_resource_lifetime(archive, tmp_path, failure):
    # Exercise the actual lightweight entrypoint without importing GPU models.
    source = Path(__file__).resolve().parents[1] / 'run.py'
    tree = ast.parse(source.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    roots = []

    def pipeline(resources):
        root = resources.enter_context(prepared_depth(archive[0], tmp_path))
        roots.append(root)
        assert root.exists()
        if failure == 'error':
            raise RuntimeError('consumer failed')
        if failure == 'interrupt':
            raise KeyboardInterrupt
        if failure == 'sigterm':
            signal.raise_signal(signal.SIGTERM)
        return 42

    scope = {'ExitStack': ExitStack, 'signal': signal, '_run': pipeline}
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(source), 'exec'), scope)
    previous = signal.getsignal(signal.SIGTERM)
    if failure:
        with pytest.raises(RuntimeError if failure == 'error' else KeyboardInterrupt):
            scope['main']()
    else:
        assert scope['main']() == 42
    assert signal.getsignal(signal.SIGTERM) == previous
    assert roots and not roots[0].exists()
