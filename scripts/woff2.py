# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Repackage a TTF font as WOFF2 and prove nothing but the packaging changed.

Usage: python3 scripts/woff2.py <input.ttf> <output.woff2>

The SIL OFL FAQ (2.2) lets a font be repackaged under its original name only
if its data is unchanged and no metadata is added, so this refuses to write
anything that does not round-trip exactly.
"""

import sys

from fontTools.ttLib import TTFont


def outlines(font):
    glyf = font["glyf"]
    return {
        name: glyf[name].getCoordinates(glyf)[0].array.tolist()
        for name in font.getGlyphOrder()
    }


def names(font):
    return [(n.nameID, n.platformID, n.toUnicode()) for n in font["name"].names]


def main(source, target):
    font = TTFont(source)
    font.flavor = "woff2"
    font.save(target)

    original, packed = TTFont(source), TTFont(target)
    problems = [
        what
        for what, same in (
            ("character map", original.getBestCmap() == packed.getBestCmap()),
            ("names", names(original) == names(packed)),
            ("glyph outlines", outlines(original) == outlines(packed)),
            ("metadata", packed.reader.metaLength == 0),
        )
        if not same
    ]
    if problems:
        sys.exit(f"woff2.py: {', '.join(problems)} changed; refusing {target}")
    print(f"{target}: {len(original.getGlyphOrder())} glyphs, unchanged")


if __name__ == "__main__":
    main(*sys.argv[1:])
