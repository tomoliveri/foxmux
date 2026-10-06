/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

/* exported DEFAULT_SETTINGS, loadSettings, terminalFontFamily */

const DEFAULT_SETTINGS = {
  startDir: "~",
  sessionMode: "per-tab", // "per-tab" | "shared"
  sessionName: "main",
  fontSize: 14,
  fontFamily: "Menlo, 'SF Mono', Monaco, 'DejaVu Sans Mono'",
  optionIsMeta: false,
};

// The bundled Nerd Fonts symbols font (see terminal.css) supplies the icons that
// tools like eza and starship print, whatever font the user picks.
function terminalFontFamily(settings) {
  return `${settings.fontFamily}, "foxmux symbols", monospace`;
}

async function loadSettings() {
  const stored = await browser.storage.local.get(DEFAULT_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...stored };
}
