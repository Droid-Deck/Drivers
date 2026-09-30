#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

PATCHES = Path(__file__).resolve().parent.parent / 'patches'
TARGETS = ('android', 'linux')


def series(target):
    return [e for e in json.loads((PATCHES / 'series.json').read_text()) if target in e['targets']]


def apply(target, mesa):
    for entry in series(target):
        path = PATCHES / entry['file']
        print(f'== {entry["file"]}', flush=True)
        if path.suffix == '.py':
            subprocess.run([sys.executable, str(path)], cwd=mesa, check=True)
        else:
            subprocess.run(['git', 'apply', '--whitespace=nowarn', str(path)], cwd=mesa, check=True)


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in TARGETS:
        sys.exit(f'usage: apply_patches.py {{{"|".join(TARGETS)}}} <mesa>')
    apply(*sys.argv[1:])
