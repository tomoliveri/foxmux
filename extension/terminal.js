/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

// Must match the "name" in the native host manifest written by install.sh.
const HOST_NAME = "foxmux";
// Must match PROTOCOL in native/foxmux_host.py.
const PROTOCOL = 1;

const COLOR_WARNING = "33";
const COLOR_ERROR = "31";
const COLOR_HINT = "90";

function base64ToBytes(b64) {
  return Uint8Array.from(atob(b64), c => c.charCodeAt(0));
}

async function main() {
  const settings = await loadSettings();
  // Load the icon font up front so xterm.js measures cells with it in place.
  await document.fonts.load('16px "foxmux symbols"', "");
  const container = document.getElementById("terminal");

  const term = new Terminal({
    fontSize: Number(settings.fontSize) || 14,
    fontFamily: terminalFontFamily(settings),
    macOptionIsMeta: settings.optionIsMeta,
    macOptionClickForcesSelection: true,
    scrollback: 0, // tmux keeps the scrollback
    linkHandler: { activate: openLink },
    theme: { background: "#1d1f21", foreground: "#e6e6e6" },
  });
  const fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(container);
  fitAddon.fit();
  term.focus();

  // One native host serves the tab for its whole life. While tmux runs,
  // keystrokes go to it; otherwise Enter (re)starts it.
  let port = null;
  let running = false;
  let hostExplained = false; // the host already said why it is stopping
  let session = "";

  function show(messageName, color, args = []) {
    const text = browser.i18n.getMessage(messageName, args) || messageName;
    term.write(`\r\n\x1b[${color}m${text}\x1b[0m\r\n`);
  }

  function setTitle(title) {
    document.title =
      title || browser.i18n.getMessage("terminalTitle", session || "…");
  }

  function sendToTmux(message) {
    if (running) {
      port.postMessage(message);
    }
  }

  function onHostMessage(message) {
    switch (message.type) {
      case "ready":
        if (message.protocol !== PROTOCOL) {
          // Hosts from before the protocol check send no number at all.
          const hostIsOlder = !(message.protocol > PROTOCOL);
          show(hostIsOlder ? "hostOutdated" : "addonOutdated", COLOR_ERROR);
          port.disconnect();
          port = null;
          return;
        }
        running = true;
        session = message.session;
        setTitle();
        break;
      case "output":
        term.write(base64ToBytes(message.data));
        break;
      case "notice":
        show(message.code, COLOR_WARNING, message.args);
        break;
      case "error":
        hostExplained = true;
        show(message.code, COLOR_ERROR, message.args);
        break;
      case "exit":
        running = false;
        show("tmuxExited", COLOR_HINT);
        break;
    }
  }

  function onHostGone() {
    running = false;
    port = null;
    if (!hostExplained) {
      show("hostUnreachable", COLOR_ERROR);
    }
    hostExplained = false;
  }

  function start() {
    term.reset();
    if (!port) {
      port = browser.runtime.connectNative(HOST_NAME);
      port.onMessage.addListener(onHostMessage);
      port.onDisconnect.addListener(onHostGone);
    }
    port.postMessage({
      type: "open",
      cwd: settings.startDir,
      cols: term.cols,
      rows: term.rows,
      session: settings.sessionMode === "shared" ? settings.sessionName : "",
      persist: settings.sessionMode === "shared",
    });
  }

  term.onData(data => {
    if (running) {
      sendToTmux({ type: "input", data });
    } else if (data === "\r") {
      start();
    }
  });
  // Some mouse reports arrive as raw bytes rather than text.
  term.onBinary(data => sendToTmux({ type: "input", data, binary: true }));
  term.onResize(({ cols, rows }) => sendToTmux({ type: "resize", cols, rows }));
  term.onTitleChange(setTitle);
  new ResizeObserver(() => fitAddon.fit()).observe(container);

  setTitle();
  start();
}

main();
