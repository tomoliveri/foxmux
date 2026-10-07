#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Packages the extension as dist/foxmux-<version>.xpi (unsigned), with the
# licence files included so they travel with every copy.

set -eu
cd "$(dirname "$0")/.."
npm run --silent vendor
VERSION=$(python3 -c 'import json;print(json.load(open("extension/manifest.json"))["version"])')
OUT="dist/foxmux-$VERSION.xpi"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p dist
cp -R extension/. "$STAGE/"
cp LICENSE NOTICE.md "$STAGE/"
cp -R licenses "$STAGE/licenses"
rm -f dist/foxmux-*[0-9].xpi
(cd "$STAGE" && zip -qr -X "$OLDPWD/$OUT" . -x '.*')
echo "$OUT"
