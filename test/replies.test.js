/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Unit tests for extension/replies.js, which spots the terminal's answers to
// colour queries so late ones can be dropped.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const context = vm.createContext({});
vm.runInContext(readFileSync("extension/replies.js", "utf8"), context);
const { isColourReply } = context;

test("palette and default colour replies are recognised", () => {
  assert.ok(isColourReply("\x1b]4;38;rgb:0000/afaf/d7d7\x1b\\"));
  assert.ok(isColourReply("\x1b]4;205;rgb:ffff/5f5f/afaf\x07"));
  assert.ok(isColourReply("\x1b]10;rgb:e6e6/e6e6/e6e6\x1b\\"));
  assert.ok(isColourReply("\x1b]11;rgb:1d1d/1f1f/2121\x07"));
});

test("typed text and other replies pass through", () => {
  assert.ok(!isColourReply("rgb:0000/afaf/d7d7"));
  assert.ok(!isColourReply("\x1b[?1;2c"));
  assert.ok(!isColourReply("\x1b]52;c;aGVsbG8=\x07"));
  assert.ok(!isColourReply("\x1b]4;38;rgb:0000/afaf/d7d7\x1b\\ls\r"));
});
