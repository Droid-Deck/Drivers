import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from turnip_changed import decide

MESA = 'a' * 40


def release(recipe='r1', body=f'**Mesa:** 26.3 @ [`x`](https://gitlab.freedesktop.org/mesa/mesa/-/commit/{MESA})'):
    return {'tag_name': 'DD-Turnip-v0.2.0', 'target_commitish': recipe, 'body': body,
            'published_at': '2026-10-11T04:11:10Z', 'draft': False, 'prerelease': False}


class TurnipChangedTest(unittest.TestCase):
    def test_first_release_builds(self):
        self.assertTrue(decide(None, MESA, 'r1')[0])

    def test_a_new_recipe_builds_even_without_mesa_changes(self):
        self.assertTrue(decide(release(recipe='r0'), MESA, 'r1', lambda r, c: [])[0])

    def test_unchanged_turnip_skips(self):
        build, reason = decide(release(), MESA, 'r1', lambda r, c: [])
        self.assertFalse(build)
        self.assertIn('no Turnip', reason)

    def test_turnip_commits_build(self):
        self.assertTrue(decide(release(), 'b' * 40, 'r1', lambda r, c: [('c' * 40, 'tu: fix')])[0])

    def test_unreadable_history_builds(self):
        def broken(r, c):
            raise subprocess.CalledProcessError(128, 'git')
        self.assertTrue(decide(release(), 'b' * 40, 'r1', broken)[0])

    def test_a_release_without_its_mesa_commit_builds(self):
        self.assertTrue(decide(release(body=''), 'b' * 40, 'r1')[0])


if __name__ == '__main__':
    unittest.main()
