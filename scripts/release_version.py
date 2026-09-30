#!/usr/bin/env python3
import json
import re
import sys

PREFIX = 'DD-Turnip-v'
TAG = re.compile(re.escape(PREFIX) + r'(\d+)\.(\d+)\.(\d+)')
INITIAL = (0, 1, 0)


def parse(tag):
    match = TAG.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else None


def latest_release(releases):
    published = [r for r in releases if not r['draft'] and not r['prerelease'] and parse(r['tag_name'])]
    return max(published, key=lambda r: parse(r['tag_name']), default=None)


def next_version(current, hotfix):
    if current is None:
        return INITIAL
    major, minor, patch = current
    if hotfix:
        return major, minor, patch + 1
    if minor == 9:
        return major + 1, 0, 0
    return major, minor + 1, 0


def version_string(version):
    return '.'.join(map(str, version))


if __name__ == '__main__':
    hotfix = sys.argv[1] == 'true'
    latest = latest_release([r for page in json.load(sys.stdin) for r in page])
    version = version_string(next_version(parse(latest['tag_name']) if latest else None, hotfix))
    print(f'version={version}')
    print(f'tag={PREFIX}{version}')
