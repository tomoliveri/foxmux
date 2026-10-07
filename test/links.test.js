/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Unit tests for extension/links.js, which decides which links printed in
// the terminal may be opened.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

function loadLinks() {
  const opened = [];
  const context = vm.createContext({
    URL,
    browser: { tabs: { create: ({ url }) => opened.push(url) } },
  });
  vm.runInContext(readFileSync("extension/links.js", "utf8"), context);
  return { ...context, opened };
}

test("plain web links are allowed", () => {
  const { safeLinkUrl } = loadLinks();
  assert.equal(safeLinkUrl("https://example.com/a"), "https://example.com/a");
  assert.equal(safeLinkUrl("http://example.com"), "http://example.com/");
});

test("anything else is refused", () => {
  const { safeLinkUrl } = loadLinks();
  for (const uri of [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "moz-extension://0f0c5e2a/options.html",
    "file:///etc/passwd",
    "about:config",
    "not a url",
    "",
  ]) {
    assert.equal(safeLinkUrl(uri), null, uri);
  }
});

test("openLink only opens allowed links, in a new tab", () => {
  const { openLink, opened } = loadLinks();
  openLink(null, "javascript:alert(1)");
  openLink(null, "https://example.com/");
  assert.deepEqual(opened, ["https://example.com/"]);
});
