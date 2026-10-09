"""Prepare lossless archived depth once for all PNG-based pipeline stages."""

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile


def inspect_depth(source):
    source = Path(source)
    for relative in ('fast_foundation/depth_uint16_png', 'depth_uint16_png',
                     'fast_foundation_archive/depth_uint16_png'):
        if (source / relative).is_dir():
            return None
    root = next((p for p in (source / 'fast_foundation', source)
                 if (p / 'depth_archive_meta.json').is_file()), None)
    if root is None:
        raise ValueError(f'No depth PNG directory or supported FFV1 archive under {source}')
    meta = json.loads((root / 'depth_archive_meta.json').read_text())
    ffv1 = meta.get('ffv1', {})
    expected = {'enabled': True, 'codec': 'ffv1', 'pixel_format': 'gray16le',
                'bit_depth': 16, 'depth_unit': 'millimeter', 'invalid_value': 0,
                'lossless': True}
    if (meta.get('stage') != 'depth_archive_v1' or meta.get('unit') != 'millimeter'
            or meta.get('encoding') != 'uint16' or meta.get('invalid_value') != 0
            or any(ffv1.get(k) != v for k, v in expected.items())):
        raise ValueError('Unsupported depth archive: expected lossless uint16 millimeter FFV1, invalid=0')
    for key in ('frame_count', 'width', 'height'):
        if type(ffv1.get(key)) is not int or ffv1[key] <= 0:
            raise ValueError(f'Invalid FFV1 {key}')
    if (meta.get('frame_count') != ffv1['frame_count'] or
            [r.get('frame_idx') for r in meta.get('frames', [])] != list(range(ffv1['frame_count']))):
        raise ValueError('Depth archive frame indices/count disagree')
    names = {'avi': 'depth_uint16_ffv1.avi', 'mkv': 'depth_ffv1.mkv'}
    if ffv1.get('container') not in names:
        raise ValueError('Unsupported FFV1 container')
    # Archive metadata may contain paths from another machine; never follow them.
    archive = root / names[ffv1['container']]
    calibration = root / 'fast_foundation_stereo_video_meta.json'
    for path in (archive, calibration):
        if not path.is_file():
            raise FileNotFoundError(path)
    for tool in ('ffmpeg', 'ffprobe'):
        if shutil.which(tool) is None:
            raise RuntimeError(f'{tool} is required for archived depth')
    return archive, calibration, ffv1


@contextmanager
def prepared_depth(source, output, *, expected_frames=None):
    info = inspect_depth(source)
    if info is None:
        yield Path(source)
        return
    archive, calibration, spec = info
    if expected_frames is not None and spec['frame_count'] != expected_frames:
        raise ValueError('Depth archive and input image frame counts disagree')
    probe = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,pix_fmt,width,height', '-of', 'json', str(archive),
    ], check=True, capture_output=True, text=True)
    streams = json.loads(probe.stdout)['streams']
    if len(streams) != 1 or any(streams[0].get(k) != v for k, v in {
        'codec_name': 'ffv1', 'pix_fmt': 'gray16le',
        'width': spec['width'], 'height': spec['height'],
    }.items()):
        raise ValueError('FFV1 stream disagrees with depth metadata')
    with tempfile.TemporaryDirectory(prefix='.hand-depth-', dir=output) as directory:
        root = Path(directory)
        png = root / 'depth_uint16_png'
        png.mkdir()
        shutil.copyfile(calibration, root / calibration.name)
        result = subprocess.run([
            'ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(archive),
            '-map', '0:v:0', '-vsync', '0', '-c:v', 'png', '-pix_fmt', 'gray16be',
            '-start_number', '0', str(png / 'frame_%06d_depth_mm.png'),
        ], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f'Depth decode failed: {result.stderr[-4000:]}')
        paths = sorted(png.glob('*.png'))
        if len(paths) != spec['frame_count']:
            raise ValueError('Decoded depth frame count disagrees with metadata')
        for index, path in enumerate(paths):
            with path.open('rb') as stream:
                header = stream.read(29)
            if (path.name != f'frame_{index:06d}_depth_mm.png' or
                    header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR' or
                    struct.unpack('>IIBB', header[16:26]) !=
                    (spec['width'], spec['height'], 16, 0)):
                raise ValueError(f'Invalid decoded uint16 depth PNG: {path}')
        yield root
