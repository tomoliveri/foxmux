/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

// Programs ask the terminal for its colours (OSC 4 palette, OSC 10-19
// foreground/background/cursor...) and wait a short while for the answer.
// Firefox throttles background tabs, so a query can sit unparsed for seconds;
// by the time xterm.js answers, the program has given up and the reply is read
// as typed text by whatever has the keyboard (usually the shell).

// A reply to a query that waited longer than this is dropped.
const STALE_REPLY_MS = 500;

const COLOUR_REPLY =
  // eslint-disable-next-line no-control-regex -- matching escape sequences
  /^\x1b\](?:4;\d+|1\d);rgb:[0-9a-f]+\/[0-9a-f]+\/[0-9a-f]+(?:\x07|\x1b\\)$/i;

function isColourReply(data) {
  return COLOUR_REPLY.test(data);
}
