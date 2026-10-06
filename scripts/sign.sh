#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Signs the extension through addons.mozilla.org on the *unlisted* channel
# (private: not published on AMO) so release Firefox will install it.
#
# Credentials come from AMO_JWT_ISSUER / AMO_JWT_SECRET, or from a git-ignored
# .amo-credentials file in the repo root that sets those two variables.

set -eu
cd "$(dirname "$0")/.."
[ -f .amo-credentials ] && . ./.amo-credentials
: "${AMO_JWT_ISSUER:?set AMO_JWT_ISSUER (https://addons.mozilla.org/developers/addon/api/key/)}"
: "${AMO_JWT_SECRET:?set AMO_JWT_SECRET}"

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R extension/. "$STAGE/"
cp LICENSE NOTICE.md "$STAGE/"
cp -R licenses "$STAGE/licenses"

mkdir -p dist
${WEB_EXT:-npx --yes web-ext} sign --no-config-discovery --source-dir "$STAGE" \
  --artifacts-dir dist --channel unlisted \
  --api-key "$AMO_JWT_ISSUER" --api-secret "$AMO_JWT_SECRET"
ls -1 dist/*.xpi
