#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Signs the extension through addons.mozilla.org on the *unlisted* channel
# (private: not published on AMO) so release Firefox will install it, and
# writes dist/foxmux-<version>-signed.xpi.
#
# Credentials come from AMO_JWT_ISSUER / AMO_JWT_SECRET, or from a git-ignored
# .amo-credentials file in the repo root that sets those two variables.

set -eu
cd "$(dirname "$0")/.."
if [ -f .amo-credentials ]; then
  # shellcheck disable=SC1091
  . ./.amo-credentials
fi
: "${AMO_JWT_ISSUER:?set AMO_JWT_ISSUER (https://addons.mozilla.org/developers/addon/api/key/)}"
: "${AMO_JWT_SECRET:?set AMO_JWT_SECRET}"
npm run --silent vendor

VERSION=$(node -p 'require("./extension/manifest.json").version')
STAGE=$(mktemp -d)
OUT=$(mktemp -d)
trap 'rm -rf "$STAGE" "$OUT"' EXIT
cp -R extension/. "$STAGE/"
cp LICENSE NOTICE.md "$STAGE/"
cp -R licenses "$STAGE/licenses"

npx web-ext sign --no-config-discovery --source-dir "$STAGE" \
  --artifacts-dir "$OUT" --channel unlisted \
  --api-key "$AMO_JWT_ISSUER" --api-secret "$AMO_JWT_SECRET"

mkdir -p dist
mv "$OUT"/*.xpi "dist/foxmux-$VERSION-signed.xpi"
echo "dist/foxmux-$VERSION-signed.xpi"
