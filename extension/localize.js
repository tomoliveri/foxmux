/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

// Fills every element marked data-l10n-id with its message from _locales.
for (const element of document.querySelectorAll("[data-l10n-id]")) {
  element.textContent = browser.i18n.getMessage(element.dataset.l10nId);
}
document.documentElement.lang = browser.i18n.getUILanguage();
