/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Copies the xterm.js release files from node_modules into extension/vendor.
// The vendor folder is generated, so `npm ci` pins exactly what ships.

import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

const files = {
  "@xterm/xterm/lib/xterm.js": "xterm.js",
  "@xterm/xterm/css/xterm.css": "xterm.css",
  "@xterm/addon-fit/lib/addon-fit.js": "addon-fit.js",
};
const licences = {
  "@xterm/xterm/LICENSE": "xterm.js-MIT.txt",
  "@xterm/addon-fit/LICENSE": "xterm-addon-fit-MIT.txt",
};

mkdirSync("extension/vendor", { recursive: true });
for (const [from, to] of Object.entries(files)) {
  // Source maps are not shipped, so drop the comments that point to them.
  const text = readFileSync(`node_modules/${from}`, "utf8");
  writeFileSync(
    `extension/vendor/${to}`,
    text.replace(/^\/\/# sourceMappingURL=.*\n?/m, "")
  );
}
for (const [from, to] of Object.entries(licences)) {
  copyFileSync(`node_modules/${from}`, `licenses/${to}`);
}
