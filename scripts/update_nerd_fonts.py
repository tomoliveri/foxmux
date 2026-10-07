# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Update the bundled Nerd Fonts symbols font to the latest release.

Usage: python3 scripts/update_nerd_fonts.py

Prints the new version, or nothing when the bundled font is already current.
When the licences that apply to the symbols font changed (its own licence, or
the table of icon sets it is built from), it also prints "licences-changed",
so a person can review them before anything merges.

The download is checked against the SHA-256 digest GitHub records for the
release asset, the font is repackaged losslessly by scripts/woff2.py, and the
licence files and NOTICE.md are refreshed from the same release. Set GH_TOKEN
to avoid GitHub API rate limits.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "ryanoasis/nerd-fonts"
ASSET = "NerdFontsSymbolsOnly.zip"
FONT = "SymbolsNerdFontMono-Regular.ttf"
LICENCES = ROOT / "licenses" / "nerd-fonts-symbols"
NOTICE = ROOT / "NOTICE.md"
# The Nerd Fonts row of the bundled-software table in NOTICE.md.
NOTICE_ROW = re.compile(r"^(\| \[Nerd Fonts\][^|]*\| )([0-9.]+)( *\|)", re.M)


def fetch(url, api=False):
    headers = {"User-Agent": "foxmux-font-update"}
    token = os.environ.get("GH_TOKEN")
    if api and token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - https only
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read()


def icon_set_licences(audit):
    """The table of icon sets in license-audit.md (the first table)."""
    rows = re.search(r"^\| Project .*?(?=\n\n)", audit, re.M | re.S)
    return rows.group(0) if rows else audit


def github(path):
    return json.loads(fetch(f"https://api.github.com/repos/{REPO}/{path}", api=True))


def main():
    current = NOTICE_ROW.search(NOTICE.read_text()).group(2)
    release = github("releases/latest")
    latest = release["tag_name"].removeprefix("v")
    if latest == current:
        return

    asset = next(a for a in release["assets"] if a["name"] == ASSET)
    digest = asset.get("digest") or ""
    if not digest.startswith("sha256:"):
        sys.exit(f"update_nerd_fonts.py: no SHA-256 digest published for {ASSET}")
    data = fetch(asset["browser_download_url"])
    if hashlib.sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        sys.exit(f"update_nerd_fonts.py: {ASSET} does not match its digest")

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / ASSET
        archive.write_bytes(data)
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extract(FONT, tmp)
            zip_file.extract("LICENSE", tmp)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "woff2.py"),
                str(Path(tmp) / FONT),
                str(ROOT / "extension" / "fonts" / FONT.replace(".ttf", ".woff2")),
            ],
            check=True,
            stdout=sys.stderr,
        )
        old_licence = (LICENCES / "LICENSE-MIT.txt").read_text()
        shutil.copy(Path(tmp) / "LICENSE", LICENCES / "LICENSE-MIT.txt")
        licences_changed = old_licence != (LICENCES / "LICENSE-MIT.txt").read_text()

    audit_url = f"https://raw.githubusercontent.com/{REPO}/v{latest}/license-audit.md"
    old_audit = (LICENCES / "license-audit.md").read_text()
    new_audit = fetch(audit_url).decode()
    (LICENCES / "license-audit.md").write_text(new_audit)
    if icon_set_licences(old_audit) != icon_set_licences(new_audit):
        licences_changed = True
    NOTICE.write_text(
        NOTICE_ROW.sub(lambda m: m.group(1) + latest + m.group(3), NOTICE.read_text())
    )
    print(latest)
    if licences_changed:
        print("licences-changed")


if __name__ == "__main__":
    main()
