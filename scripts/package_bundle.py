#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from release_version import PREFIX

LIBRARY = 'libvulkan_freedreno.so'
PLATFORMS = ('android', 'linux')
MESA_URL = 'https://gitlab.freedesktop.org/mesa/mesa'
CI_URL = 'https://github.com/Droid-Deck/Drivers-CI/releases/tag'
ROOT = Path(__file__).resolve().parent.parent
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


def notice(tag, mesa_version, mesa_commit):
    return f'''{tag}

Turnip, the Mesa freedreno Vulkan driver, built from Mesa {mesa_version} at {mesa_commit}
with the DD-Turnip patch set, for Android (android/) and Linux ARM64 (linux/).

Source: {tag}-source.tar.xz, published with these drivers at {CI_URL}/{tag}
It holds Mesa at that commit (mesa/) and the patches and build scripts that produced them (drivers/).

Licenses: Mesa is under the MIT license, with the exceptions its files name; its license texts are in
LICENSES/mesa/. The patch set is distributed under the GNU General Public License version 3
(LICENSES/GPL-3.0.txt), and so are these drivers.
'''


def license_files(mesa):
    files = {'LICENSES/GPL-3.0.txt': (ROOT / 'LICENSE').read_bytes(),
             'LICENSES/mesa/license.rst': (mesa / 'docs' / 'license.rst').read_bytes()}
    for path in sorted((mesa / 'licenses').rglob('*')):
        if path.is_file():
            files[f'LICENSES/mesa/{path.relative_to(mesa / "licenses").as_posix()}'] = path.read_bytes()
    return files


def source_archive(mesa, recipe, tag, text, dist):
    name = f'{tag}-source'
    with tempfile.TemporaryDirectory() as work:
        top = Path(work) / name
        top.mkdir()
        for repo, ref, prefix in ((mesa, 'HEAD', 'mesa/'), (ROOT, recipe, 'drivers/')):
            archive = subprocess.run(['git', '-C', str(repo), 'archive', f'--prefix={prefix}', ref], check=True, capture_output=True).stdout
            subprocess.run(['tar', '-x', '-C', str(top)], input=archive, check=True)
        (top / 'NOTICE').write_text(text)
        target = dist / f'{name}.tar.xz'
        subprocess.run(['tar', '--sort=name', '--mtime=@0', '--owner=0', '--group=0', '--numeric-owner',
                        '-C', work, '-cJf', str(target), name], check=True, env={**os.environ, 'XZ_OPT': '-9 -T0'})
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--mesa-commit', required=True)
    parser.add_argument('--mesa-version', required=True)
    parser.add_argument('--out', type=Path, default=Path('out'))
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--mesa-src', type=Path, required=True)
    parser.add_argument('--recipe', default='HEAD')
    args = parser.parse_args()
    built = subprocess.run(['git', '-C', str(args.mesa_src), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if built != args.mesa_commit:
        fail(f'--mesa-src is at {built}, expected {args.mesa_commit}')
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
    text = notice(tag, args.mesa_version, args.mesa_commit)
    files['NOTICE'] = text.encode()
    files.update(license_files(args.mesa_src))

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
    source = source_archive(args.mesa_src, args.recipe, tag, text, args.dist)
    for name in sorted(files):
        print(name)
    print(f'{bundle} {digest}')
    print(f'{source} {source.stat().st_size}')


if __name__ == '__main__':
    main()
