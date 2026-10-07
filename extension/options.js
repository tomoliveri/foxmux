/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

const form = document.getElementById("form");
const statusLine = document.getElementById("status");

function readForm() {
  const f = form.elements;
  return {
    startDir: f.startDir.value.trim() || "~",
    sessionMode: f.sessionMode.value,
    sessionName: f.sessionName.value.trim() || "main",
    fontSize: Number(f.fontSize.value) || DEFAULT_SETTINGS.fontSize,
    fontFamily: f.fontFamily.value.trim() || DEFAULT_SETTINGS.fontFamily,
    optionIsMeta: f.optionIsMeta.checked,
  };
}

async function init() {
  const s = await loadSettings();
  const f = form.elements;
  f.startDir.value = s.startDir;
  f.sessionMode.value = s.sessionMode;
  f.sessionName.value = s.sessionName;
  f.fontSize.value = s.fontSize;
  f.fontFamily.value = s.fontFamily;
  f.optionIsMeta.checked = s.optionIsMeta;

  form.addEventListener("input", async () => {
    await browser.storage.local.set(readForm());
    statusLine.textContent = browser.i18n.getMessage("optSaved");
  });
  // Lets automated tests know the fields show the saved values.
  document.documentElement.toggleAttribute("data-loaded", true);
}

init();
