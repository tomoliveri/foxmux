#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Runs a command up to three times, for CI steps that depend on the network
# (package mirrors, git clones). Usage: scripts/retry.sh <command> [args...]

for attempt in 1 2 3; do
  "$@" && exit 0
  echo "retry.sh: attempt $attempt of 3 failed: $*" >&2
  [ "$attempt" = 3 ] || sleep $((attempt * 15))
done
exit 1
