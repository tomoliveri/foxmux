/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["extension/vendor/", "dist/"] },
  js.configs.recommended,
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
    rules: {
      eqeqeq: "error",
      "prefer-const": "error",
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
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
      },
    },
  },
];
