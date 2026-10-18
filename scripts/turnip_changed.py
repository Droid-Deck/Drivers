#!/usr/bin/env python3
import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timedelta

from release_notes import TURNIP_PATHS, fetch_history, log, previous_mesa_commit
from release_version import latest_release


def turnip_commits(release, commit):
    previous = previous_mesa_commit(release)
    if previous is None:
        return None
    if previous == commit:
        return []
    since = datetime.fromisoformat(release['published_at'].replace('Z', '+00:00')) - timedelta(days=30)
    with tempfile.TemporaryDirectory() as repo:
        fetch_history(repo, commit, since, previous)
        return log(repo, [f'{previous}..{commit}'], TURNIP_PATHS)


def decide(release, commit, recipe, commits_of=turnip_commits):
    if release is None:
        return True, 'no earlier release'
    if release.get('target_commitish') != recipe:
        return True, 'the patch set or build recipe changed'
    try:
        commits = commits_of(release, commit)
    except (subprocess.CalledProcessError, RuntimeError) as error:
        return True, f'Mesa history could not be read ({error})'
    if commits is None:
        return True, f'{release["tag_name"]} does not record its Mesa commit'
    if not commits:
        return False, f'no Turnip, Vulkan runtime or gralloc changes in Mesa since {release["tag_name"]}'
    return True, f'{len(commits)} Turnip, Vulkan runtime or gralloc commits since {release["tag_name"]}'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--releases', required=True)
    parser.add_argument('--mesa-commit', required=True)
    parser.add_argument('--recipe', required=True)
    args = parser.parse_args()
    with open(args.releases) as f:
        release = latest_release([r for page in json.load(f) for r in page])
    build, reason = decide(release, args.mesa_commit, args.recipe)
    print(f'changed={"true" if build else "false"}')
    print(f'reason={reason}')
