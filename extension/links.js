/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

/* exported openLink */

// Terminal output is untrusted, so only ever open plain web links from it.
function safeLinkUrl(uri) {
  let url;
  try {
    url = new URL(uri);
  } catch {
    return null;
  }
  return url.protocol === "http:" || url.protocol === "https:"
    ? url.href
    : null;
}

function openLink(event, uri) {
  const url = safeLinkUrl(uri);
  if (url) {
    browser.tabs.create({ url });
  }
}
