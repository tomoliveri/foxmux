# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for scripts/release-version.sh, run against throwaway git repos."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release-version.sh"


class ReleaseVersionTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        (self.repo / "scripts").mkdir()
        shutil.copy(SCRIPT, self.repo / "scripts")
        (self.repo / "extension").mkdir()
        self.git("init", "-q")
        self.set_manifest_version("0.2.0")
        self.commit("start")

    def git(self, *args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=self.repo,
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def set_manifest_version(self, version):
        (self.repo / "extension" / "manifest.json").write_text(
            '{\n  "manifest_version": 3,\n'
            f'  "version": "{version}",\n'
            '  "browser_specific_settings": { "strict_min_version": "128.0" }\n}\n'
        )

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def change(self, path):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(file.read_text() + "x" if file.exists() else "x")
        self.commit(f"change {path}")

    def next_version(self):
        return subprocess.run(
            ["sh", "scripts/release-version.sh"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_first_release_uses_the_manifest_version(self):
        self.assertEqual(self.next_version(), "0.2.0")

    def test_nothing_to_release_right_after_a_release(self):
        self.git("tag", "v0.2.0")
        self.assertEqual(self.next_version(), "")

    def test_changes_outside_shipped_files_do_not_release(self):
        self.git("tag", "v0.2.0")
        self.change("README.md")
        self.change(".github/workflows/ci.yml")
        self.assertEqual(self.next_version(), "")

    def test_shipped_changes_bump_the_patch_version(self):
        self.git("tag", "v0.2.0")
        self.change("extension/terminal.js")
        self.assertEqual(self.next_version(), "0.2.1")

    def test_native_host_and_dependency_changes_also_release(self):
        for path in ("native/foxmux_host.py", "package-lock.json", "licenses/x"):
            with self.subTest(path=path):
                self.git("tag", "-f", "v0.2.0")
                self.change(path)
                self.assertEqual(self.next_version(), "0.2.1")

    def test_patch_numbers_compare_as_numbers(self):
        self.git("tag", "v0.2.9")
        self.change("extension/terminal.js")
        self.assertEqual(self.next_version(), "0.2.10")
        self.git("tag", "v0.2.10")
        self.change("extension/terminal.js")
        self.assertEqual(self.next_version(), "0.2.11")

    def test_a_raised_manifest_version_wins(self):
        self.git("tag", "v0.2.4")
        self.set_manifest_version("0.3.0")
        self.commit("start 0.3")
        self.assertEqual(self.next_version(), "0.3.0")


if __name__ == "__main__":
    unittest.main()
