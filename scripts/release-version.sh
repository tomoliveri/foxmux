#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Prints the version the next release should have, or nothing when no
# shipped file changed since the last release tag.
#
# The version in extension/manifest.json is a floor: raise it by hand for a
# minor or major release. Otherwise the last release's patch number goes up.

set -eu
cd "$(dirname "$0")/.."

SHIPPED="extension native install.sh package-lock.json LICENSE NOTICE.md licenses"

last=$(git tag --list 'v*' --sort=-v:refname | head -n 1)
# shellcheck disable=SC2086 # SHIPPED is a list of paths
if [ -n "$last" ] && git diff --quiet "$last" HEAD -- $SHIPPED; then
  exit 0
fi

floor=$(sed -n 's/^  "version": "\(.*\)",$/\1/p' extension/manifest.json)
if [ -z "$last" ]; then
  echo "$floor"
  exit 0
fi
bumped=$(echo "${last#v}" | awk -F. '{ print $1 "." $2 "." $3 + 1 }')
printf '%s\n%s\n' "$floor" "$bumped" | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1
