import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from release_version import latest_release, next_version, parse, version_string


def release(tag, draft=False, prerelease=False):
    return {'tag_name': tag, 'draft': draft, 'prerelease': prerelease}


def bump(tag, hotfix=False):
    return version_string(next_version(parse(tag) if tag else None, hotfix))


class ReleaseVersionTest(unittest.TestCase):
    def test_initial_release(self):
        self.assertEqual(bump(None), '0.1.0')
        self.assertEqual(bump(None, hotfix=True), '0.1.0')

    def test_weekly_bumps_minor_and_resets_patch(self):
        self.assertEqual(bump('DD-Turnip-v0.1.0'), '0.2.0')
        self.assertEqual(bump('DD-Turnip-v0.1.5'), '0.2.0')
        self.assertEqual(bump('DD-Turnip-v0.8.0'), '0.9.0')
        self.assertEqual(bump('DD-Turnip-v1.0.0'), '1.1.0')

    def test_minor_rolls_over_into_major(self):
        self.assertEqual(bump('DD-Turnip-v0.9.0'), '1.0.0')
        self.assertEqual(bump('DD-Turnip-v0.9.4'), '1.0.0')
        self.assertEqual(bump('DD-Turnip-v1.9.2'), '2.0.0')

    def test_hotfix_bumps_patch_only(self):
        self.assertEqual(bump('DD-Turnip-v0.1.0', hotfix=True), '0.1.1')
        self.assertEqual(bump('DD-Turnip-v0.1.1', hotfix=True), '0.1.2')
        self.assertEqual(bump('DD-Turnip-v0.9.0', hotfix=True), '0.9.1')
        self.assertEqual(bump('DD-Turnip-v1.0.9', hotfix=True), '1.0.10')

    def test_sequence(self):
        tag, seen = None, []
        for hotfix in [False] * 3 + [True, True] + [False] * 8:
            version = bump(tag, hotfix)
            seen.append(version)
            tag = f'DD-Turnip-v{version}'
        self.assertEqual(seen, ['0.1.0', '0.2.0', '0.3.0', '0.3.1', '0.3.2', '0.4.0', '0.5.0',
                                '0.6.0', '0.7.0', '0.8.0', '0.9.0', '1.0.0', '1.1.0'])

    def test_latest_ignores_drafts_prereleases_and_foreign_tags(self):
        latest = latest_release([
            release('DD-Turnip-v0.1.9'),
            release('DD-Turnip-v0.1.10'),
            release('DD-Turnip-v0.3.0', draft=True),
            release('DD-Turnip-v0.4.0', prerelease=True),
            release('v9.9.9'),
            release('DD-Turnip-v0.2'),
        ])
        self.assertEqual(latest['tag_name'], 'DD-Turnip-v0.1.10')
        self.assertIsNone(latest_release([release('DD-Turnip-v0.1.0', draft=True)]))


if __name__ == '__main__':
    unittest.main()
