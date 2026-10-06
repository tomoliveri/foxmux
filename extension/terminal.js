/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

"use strict";

// Must match the "name" in the native host manifest written by install.sh.
const HOST_NAME = "foxmux";

function base64ToBytes(b64) {
  return Uint8Array.from(atob(b64), c => c.charCodeAt(0));
}

// Terminal output is untrusted, so only ever open plain web links from it.
function openLink(event, uri) {
  let url;
  try {
    url = new URL(uri);
  } catch {
    return;
  }
  if (url.protocol === "http:" || url.protocol === "https:") {
    browser.tabs.create({ url: url.href });
  }
}

async function main() {
  const settings = await loadSettings();
  // Load the icon font up front so xterm.js measures cells with it in place.
  await document.fonts.load('16px "foxmux symbols"', "\ue5ff");
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

  let port = null;
  let connected = false;
  let session = settings.sessionMode === "shared" ? settings.sessionName : "";

  function showMessage(text, color = "33") {
    term.write(`\r\n\x1b[${color}m${text}\x1b[0m\r\n`);
  }

  function send(message) {
    if (connected) {
      port.postMessage(message);
    }
  }

  function connect() {
    term.reset();
    port = browser.runtime.connectNative(HOST_NAME);
    connected = true;
    let finished = false;

    port.onMessage.addListener(message => {
      switch (message.type) {
        case "ready":
          // Remember the name so reconnecting reattaches to the same session.
          session = message.session;
          document.title = `tmux — ${session}`;
          break;
        case "output":
          term.write(base64ToBytes(message.data));
          break;
        case "notice":
          showMessage(message.message);
          break;
        case "error":
          finished = true;
          showMessage(message.message, "31");
          break;
        case "exit":
          finished = true;
          showMessage("[tmux exited — press Enter to reconnect]", "90");
          break;
      }
    });

    port.onDisconnect.addListener(() => {
      connected = false;
      if (!finished) {
        showMessage("foxmux could not reach its native host.", "31");
        showMessage("Run ./install.sh, then press Enter to retry.", "90");
      }
    });

    port.postMessage({
      type: "open",
      cwd: settings.startDir,
      cols: term.cols,
      rows: term.rows,
      session,
      persist: settings.sessionMode === "shared",
    });
  }

  term.onData(data => {
    if (connected) {
      send({ type: "input", data });
    } else if (data === "\r") {
      connect();
    }
  });
  // Some mouse reports arrive as raw bytes rather than text.
  term.onBinary(data => send({ type: "input", data, binary: true }));
  term.onResize(({ cols, rows }) => send({ type: "resize", cols, rows }));
  term.onTitleChange(title => {
    document.title = title || `tmux — ${session}`;
  });
  new ResizeObserver(() => fitAddon.fit()).observe(container);

  connect();
}

main();
