/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

browser.action.onClicked.addListener(tab => {
  browser.tabs.create({
    url: browser.runtime.getURL("tmux.html"),
    index: tab ? tab.index + 1 : undefined,
  });
});
