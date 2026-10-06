/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// End-to-end test: installs the extension in a real Firefox, opens a terminal
// tab and drives tmux through it. Needs tmux, the native host (./install.sh)
// and an unsigned build (npm run build). Set FIREFOX_BIN to pick a Firefox.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { after, before, test } from "node:test";
import { Builder, By, Key } from "selenium-webdriver";
import firefox from "selenium-webdriver/firefox.js";

const EXTENSION_ID = "foxmux@foxmux";
const UUID = "0f0c5e2a-7d1b-4c8e-9a6f-3b2d1e0f4a5c";
const BASE = `moz-extension://${UUID}`;

let driver;

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function waitFor(what, check, timeout = 20000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    last = await check();
    if (last) {
      return last;
    }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${what}`);
}

// WebDriver may not navigate to extension pages, so load them the way the
// browser UI would, from privileged chrome code.
async function openPage(path) {
  await driver.setContext(firefox.Context.CHROME);
  await driver.executeScript(
    `gBrowser.selectedBrowser.fixupAndLoadURIString(arguments[0], {
       triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal(),
     });`,
    `${BASE}/${path}`
  );
  await driver.setContext(firefox.Context.CONTENT);
  await waitFor(path, async () =>
    (await driver.getCurrentUrl()).endsWith(path)
  );
}

async function screenLines() {
  const text = await driver.executeScript(
    "return document.querySelector('.xterm-rows')?.innerText ?? ''"
  );
  return text.split("\n");
}

async function openTerminal() {
  await openPage("tmux.html");
  // tmux's status bar shows the session name once it is up.
  const title = await waitFor("tmux to start", async () => {
    const t = await driver.getTitle();
    const lines = await screenLines();
    return lines.some(l => l.includes("[foxmux-")) && t;
  });
  return title.replace("tmux — ", "");
}

async function run(command) {
  const input = await driver.findElement(By.css(".xterm-helper-textarea"));
  await input.sendKeys(command, Key.ENTER);
}

function sessionExists(name) {
  try {
    execFileSync("tmux", ["has-session", "-t", `=${name}`], {
      stdio: "ignore",
    });
    return true;
  } catch {
    return false;
  }
}

before(async () => {
  const xpi = readdirSync("dist").find(f => /^foxmux-[\d.]+\.xpi$/.test(f));
  assert.ok(xpi, "run `npm run build` first");

  const options = new firefox.Options()
    .addArguments("-headless")
    .setPreference(
      "extensions.webextensions.uuids",
      JSON.stringify({ [EXTENSION_ID]: UUID })
    );
  if (process.env.FIREFOX_BIN) {
    options.setBinary(process.env.FIREFOX_BIN);
  }
  driver = await new Builder()
    .forBrowser("firefox")
    .setFirefoxOptions(options)
    .setFirefoxService(
      new firefox.ServiceBuilder().addArguments("--allow-system-access")
    )
    .build();
  await driver.installAddon(resolve("dist", xpi), true);
});

after(async () => {
  await driver?.quit();
});

test("opens tmux in the home directory", async () => {
  await openTerminal();
  await run("pwd");
  await waitFor("pwd output", async () =>
    (await screenLines()).some(l => l.trim() === homedir())
  );
});

test("runs commands typed into the tab", async () => {
  await openTerminal();
  await run("echo foxmux-$((6 * 7))");
  await waitFor("echo output", async () =>
    (await screenLines()).some(l => l.trim() === "foxmux-42")
  );
});

test("starts in the directory chosen in preferences", async () => {
  const dir = mkdtempSync(join(homedir(), ".foxmux-e2e-"));
  try {
    await openPage("options.html");
    const field = await driver.findElement(By.name("startDir"));
    await field.clear();
    await field.sendKeys(dir);
    await waitFor("settings to save", async () =>
      (await driver.findElement(By.id("status")).getText()).includes("Saved")
    );

    await openTerminal();
    await run("pwd");
    await waitFor("pwd output", async () =>
      (await screenLines()).some(l => l.trim() === dir)
    );
  } finally {
    await openPage("options.html");
    const field = await driver.findElement(By.name("startDir"));
    await field.clear();
    await field.sendKeys("~");
    rmSync(dir, { recursive: true, force: true });
  }
});

test("closing the tab ends its tmux session", async () => {
  const session = await openTerminal();
  assert.ok(sessionExists(session), `${session} should be running`);
  await driver.get("about:blank");
  await waitFor("session to end", () => !sessionExists(session));
});
