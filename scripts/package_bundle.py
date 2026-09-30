#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from release_version import PREFIX

LIBRARY = 'libvulkan_freedreno.so'
PLATFORMS = ('android', 'linux')
MESA_URL = 'https://gitlab.freedesktop.org/mesa/mesa'
PWR_MAX = b'Failed to set initial PWR_MAX constraint'
ABI = {
    'android': {'libc': 'bionic', 'needed': 'libc.so', 'markers': [b'Using IMapper v5 stable-C API via SP-HAL']},
    'linux': {'libc': 'glibc', 'needed': 'libc.so.6', 'markers': [b'vkCreateWaylandSurfaceKHR', b'vkCreateXcbSurfaceKHR']},
}


def fail(message):
    sys.exit(f'package_bundle: {message}')


def verify(platform, library):
    data = library.read_bytes()
    header = subprocess.check_output(['readelf', '-h', str(library)], text=True)
    dynamic = subprocess.check_output(['readelf', '-d', str(library)], text=True)
    needed = set(re.findall(r'\(NEEDED\)\s+Shared library: \[(.+?)\]', dynamic))
    abi = ABI[platform]
    if 'AArch64' not in header or 'DYN' not in header:
        fail(f'{platform}: not an AArch64 shared object')
    if abi['needed'] not in needed or {'libc.so', 'libc.so.6'} - {abi['needed']} & needed:
        fail(f'{platform}: wrong libc, NEEDED {sorted(needed)}')
    for marker in abi['markers']:
        if marker not in data:
            fail(f'{platform}: missing {marker.decode()}')
    if platform == 'linux' and b'drirc.d' in data:
        fail(f'{platform}: reads driver defaults from disk')
    if PWR_MAX not in data:
        fail(f'{platform}: missing the PWR_MAX performance patch')
    return hashlib.sha256(data).hexdigest()


def driver_meta(platform, version, mesa_version, mesa_commit, digest):
    name = f'DD-Turnip v{version}'
    description = f'DroidDeck Turnip {version}, Mesa {mesa_version} ({mesa_commit[:10]})'
    driver_version = f'{PREFIX}{version}'
    if platform == 'android':
        return {
            'schemaVersion': 1,
            'name': name,
            'description': description,
            'author': 'DroidDeck',
            'packageVersion': '1',
            'vendor': 'Mesa',
            'driverVersion': driver_version,
            'minApi': 29,
            'libraryName': LIBRARY,
        }
    return {
        'schemaVersion': 1,
        'name': name,
        'description': description,
        'author': 'DroidDeck',
        'platform': 'linux',
        'architecture': 'aarch64',
        'libc': 'glibc',
        'wsi': ['wayland', 'x11'],
        'driverVersion': driver_version,
        'libraryName': LIBRARY,
        'mesaVersion': mesa_version,
        'mesaCommit': mesa_commit,
        'librarySha256': digest,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--mesa-commit', required=True)
    parser.add_argument('--mesa-version', required=True)
    parser.add_argument('--out', type=Path, default=Path('out'))
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        fail(f'bad version {args.version}')

    tag = f'{PREFIX}{args.version}'
    files = {}
    manifest = {
        'schemaVersion': 1,
        'package': 'DD-Turnip',
        'version': args.version,
        'tag': tag,
        'mesa': {'version': args.mesa_version, 'commit': args.mesa_commit, 'source': MESA_URL},
        'drivers': {},
    }
    for platform in PLATFORMS:
        source = args.out / platform
        built_from = (source / 'mesa-commit').read_text().strip()
        if built_from != args.mesa_commit:
            fail(f'{platform} was built from Mesa {built_from}, expected {args.mesa_commit}')
        digest = verify(platform, source / LIBRARY)
        meta = driver_meta(platform, args.version, args.mesa_version, args.mesa_commit, digest)
        files[f'{platform}/{LIBRARY}'] = (source / LIBRARY).read_bytes()
        files[f'{platform}/meta.json'] = (json.dumps(meta, indent=2) + '\n').encode()
        manifest['drivers'][platform] = {
            'path': platform,
            'library': f'{platform}/{LIBRARY}',
            'meta': f'{platform}/meta.json',
            'architecture': 'aarch64',
            'libc': ABI[platform]['libc'],
            'sha256': digest,
        }
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()

    args.dist.mkdir(parents=True, exist_ok=True)
    bundle = args.dist / f'{tag}.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), files[name], zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(bundle) as archive:
        if sorted(archive.namelist()) != sorted(files) or archive.testzip() is not None:
            fail('bundle does not read back intact')
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (args.dist / f'{bundle.name}.sha256').write_text(f'{digest}  {bundle.name}\n')
    for name in sorted(files):
        print(name)
    print(f'{bundle} {digest}')


if __name__ == '__main__':
    main()
