/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// Mozilla's own lint rules (as used in Firefox), plus the globals each part
// of the project runs with.

import globals from "globals";
import mozilla from "eslint-plugin-mozilla";

export default [
  // HTML is skipped: the pages have no inline scripts (CSP forbids them).
  { ignores: ["extension/vendor/", "dist/", "node_modules/", "**/*.html"] },
  ...mozilla.configs["flat/recommended"],
  {
    files: ["extension/**/*.js"],
    languageOptions: {
      sourceType: "script",
      globals: {
        ...globals.browser,
        ...globals.webextensions,
        Terminal: "readonly",
        FitAddon: "readonly",
      },
    },
  },
  {
    // Shared helpers from settings.js.
    files: ["extension/options.js", "extension/terminal.js"],
    languageOptions: {
      globals: {
        DEFAULT_SETTINGS: "readonly",
        loadSettings: "readonly",
        terminalFontFamily: "readonly",
        openLink: "readonly",
      },
    },
  },
  {
    files: ["scripts/**/*.js", "test/**/*.js", "eslint.config.mjs"],
    languageOptions: { globals: globals.node },
  },
];
