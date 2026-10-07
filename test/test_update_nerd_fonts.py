# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for scripts/update_nerd_fonts.py against the repository's real files,
so a reformatted NOTICE.md or licence audit can't silently break updates."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "update_nerd_fonts", ROOT / "scripts" / "update_nerd_fonts.py"
)
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)

AUDIT = (ROOT / "licenses" / "nerd-fonts-symbols" / "license-audit.md").read_text()


class NoticeTests(unittest.TestCase):
    def test_finds_the_bundled_version(self):
        match = update.NOTICE_ROW.search((ROOT / "NOTICE.md").read_text())
        self.assertIsNotNone(match, "Nerd Fonts row not found in NOTICE.md")
        self.assertRegex(match.group(2), r"^\d+\.\d+\.\d+$")

    def test_replaces_only_the_version(self):
        notice = (ROOT / "NOTICE.md").read_text()
        current = update.NOTICE_ROW.search(notice).group(2)
        updated = update.NOTICE_ROW.sub(
            lambda m: m.group(1) + "9.9.9" + m.group(3), notice
        )
        self.assertEqual(update.NOTICE_ROW.search(updated).group(2), "9.9.9")
        self.assertEqual(updated.replace("9.9.9", current, 1), notice)


class IconSetLicenceTests(unittest.TestCase):
    def test_extracts_the_icon_set_table(self):
        table = update.icon_set_licences(AUDIT)
        self.assertTrue(table.startswith("| Project"))
        self.assertIn("Font Awesome", table)
        self.assertNotIn("Cousine", table)  # a patched base font, not ours

    def test_ignores_changes_to_other_tables(self):
        changed = AUDIT.replace("| Cousine ", "| Cousine2")
        self.assertNotEqual(changed, AUDIT)
        self.assertEqual(
            update.icon_set_licences(changed), update.icon_set_licences(AUDIT)
        )

    def test_notices_icon_set_licence_changes(self):
        changed = AUDIT.replace("| Octicons ", "| Octicons (GPL) ")
        self.assertNotEqual(changed, AUDIT)
        self.assertNotEqual(
            update.icon_set_licences(changed), update.icon_set_licences(AUDIT)
        )


if __name__ == "__main__":
    unittest.main()
