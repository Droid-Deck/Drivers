#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

from apply_patches import PATCHES, TARGETS
from release_version import latest_release

MESA_URL = 'https://gitlab.freedesktop.org/mesa/mesa'
MESA_GIT = f'{MESA_URL}.git'
TURNIP_PATHS = ('src/freedreno', 'src/vulkan', 'src/util/u_gralloc')
INITIAL_WINDOW_DAYS = 30
BODY_BUDGET = 110000


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], check=True, capture_output=True, text=True).stdout


def fetch_history(repo, commit, since, previous):
    git(repo, 'init', '-q')
    git(repo, 'fetch', '-q', '--filter=blob:none', f'--shallow-since={since:%Y-%m-%d}', MESA_GIT, commit)
    for _ in range(5):
        if not previous or subprocess.run(['git', '-C', repo, 'cat-file', '-e', f'{previous}^{{commit}}']).returncode == 0:
            return
        git(repo, 'fetch', '-q', '--filter=blob:none', '--deepen=5000', MESA_GIT, commit)
    raise RuntimeError(f'Mesa commit {previous} not found in the history of {commit}')


def log(repo, revisions, paths=()):
    out = git(repo, 'log', '--no-merges', '--format=%H%x09%s', *revisions, '--', *paths)
    return [line.split('\t', 1) for line in out.splitlines()]


def bullets(commits):
    return [f'- {subject} ([`{sha[:10]}`]({MESA_URL}/-/commit/{sha}))' for sha, subject in commits]


def previous_mesa_commit(release):
    match = re.search(r'mesa/mesa/-/commit/([0-9a-f]{40})', release['body'] or '')
    return match.group(1) if match else None


def patch_table():
    rows = ['| Patch | Android | Linux | Change |', '|---|:-:|:-:|---|']
    for entry in json.loads((PATCHES / 'series.json').read_text()):
        marks = ['✓' if t in entry['targets'] else '' for t in TARGETS]
        rows.append(f'| `{entry["file"]}` | {marks[0]} | {marks[1]} | {entry["summary"]} |')
    return rows


def mesa_section(repo, commit, previous_release, previous):
    if previous_release is None:
        since = datetime.now(timezone.utc) - timedelta(days=INITIAL_WINDOW_DAYS)
        fetch_history(repo, commit, since, None)
        commits = log(repo, [f'--since={since:%Y-%m-%d}', commit], TURNIP_PATHS)
        return [
            '## Mesa changes in this build',
            '',
            f'First release. Turnip, Vulkan runtime and gralloc changes merged into Mesa main in the '
            f'{INITIAL_WINDOW_DAYS} days up to the build commit ({len(commits)} commits):',
            '',
            *bullets(commits),
        ], []
    tag = previous_release['tag_name']
    if previous is None:
        return [f'## Mesa upstream changes since {tag}', '',
                f'{tag} does not record its Mesa commit, so no upstream range is available.'], []
    if previous == commit:
        return [f'## Mesa upstream changes since {tag}', '', f'None: Mesa main is still at `{commit[:10]}`.'], []
    since = datetime.fromisoformat(previous_release['published_at'].replace('Z', '+00:00')) - timedelta(days=30)
    fetch_history(repo, commit, since, previous)
    everything = log(repo, [f'{previous}..{commit}'])
    turnip = log(repo, [f'{previous}..{commit}'], TURNIP_PATHS)
    head = [
        f'## Mesa upstream changes since {tag}',
        '',
        f'`{previous[:10]}` → `{commit[:10]}`: **{len(everything)} upstream commits** '
        f'([compare]({MESA_URL}/-/compare/{previous}...{commit})).',
        '',
        f'### Turnip, Vulkan runtime and gralloc ({len(turnip)})',
        '',
        *(bullets(turnip) or ['None.']),
    ]
    return head, bullets(everything)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--mesa-commit', required=True)
    parser.add_argument('--mesa-version', required=True)
    parser.add_argument('--releases', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--recipe', required=True)
    args = parser.parse_args()

    with open(args.releases) as f:
        previous_release = latest_release([r for page in json.load(f) for r in page])
    previous = previous_mesa_commit(previous_release) if previous_release else None
    commit = args.mesa_commit
    tag = f'DD-Turnip-v{args.version}'

    lines = [
        f'**Mesa:** {args.mesa_version} @ [`{commit}`]({MESA_URL}/-/commit/{commit})',
        f'**Recipe:** [`{args.recipe[:10]}`](https://github.com/{args.repo}/commit/{args.recipe})',
    ]
    if previous_release:
        lines.append(f'**Previous release:** [{previous_release["tag_name"]}]'
                     f'(https://github.com/{args.repo}/releases/tag/{previous_release["tag_name"]})')
    lines += [
        '',
        f'Turnip (Mesa freedreno Vulkan) for DroidDeck, built from the latest Mesa main with the patch set below. '
        f'`{tag}.zip` holds both drivers:',
        '',
        '| Path | Driver |',
        '|---|---|',
        '| `android/` | Android, bionic, Adrenotools `meta.json` |',
        '| `linux/` | Linux ARM64, glibc, Wayland/X11 WSI |',
        '| `manifest.json` | Both drivers with their path, libc and SHA-256 |',
        '',
        'Performance tuning: KGSL `PWR_MAX` is requested at queue creation and every 1000 submissions.',
        '',
    ]

    with tempfile.TemporaryDirectory() as repo:
        try:
            mesa, full = mesa_section(repo, commit, previous_release, previous)
        except (subprocess.CalledProcessError, RuntimeError) as error:
            mesa, full = ['## Mesa changes', '', f'Mesa history could not be read: {error}'], []
    lines += mesa + ['', '## Patches applied', '', *patch_table()]

    if full:
        budget = BODY_BUDGET - len('\n'.join(lines))
        shown = []
        for line in full:
            budget -= len(line) + 1
            if budget < 0:
                shown.append(f'- … {len(full) - len(shown)} more in the compare link above')
                break
            shown.append(line)
        lines += ['', '<details><summary>All upstream Mesa commits in this release</summary>', '', *shown, '',
                  '</details>']
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
