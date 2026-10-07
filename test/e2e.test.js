/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */

// End-to-end test: installs the extension in a real Firefox, opens a terminal
// tab and drives tmux through it. Needs tmux, the native host (./install.sh)
// and an unsigned build (npm run build). Set FIREFOX_BIN to pick a Firefox.
// Run with: npm run test:e2e

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
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

// Generous timeout: CI machines (especially macOS) can be slow. Waits end as
// soon as the condition holds, so passing tests stay fast.
// A check that throws (say, an element not there yet) counts as "not yet".
async function waitFor(what, check, timeout = 45000) {
  const end = Date.now() + timeout;
  let lastError;
  while (Date.now() < end) {
    try {
      const result = await check();
      if (result) {
        return result;
      }
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  // Show what the terminal displayed, to make CI failures easy to read.
  const screen = await screenLines().catch(() => []);
  throw new Error(
    `Timed out waiting for ${what}.` +
      (lastError ? ` Last error: ${lastError.message}.` : "") +
      ` Screen:\n${screen.join("\n")}`
  );
}

// WebDriver may not navigate to extension pages, so load them the way the
// browser UI would, from privileged chrome code.
async function openPage(path) {
  // Mark the current page so we can tell when a fresh one has replaced it,
  // even when reloading the same address.
  await driver
    .executeScript("document.documentElement.toggleAttribute('data-old', true)")
    .catch(() => {});
  await driver.setContext(firefox.Context.CHROME);
  await driver.executeScript(
    `gBrowser.selectedBrowser.fixupAndLoadURIString(arguments[0], {
       triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal(),
     });`,
    `${BASE}/${path}`
  );
  await driver.setContext(firefox.Context.CONTENT);
  await waitFor(`${path} to load`, async () => {
    if (!(await driver.getCurrentUrl()).endsWith(path)) {
      return false;
    }
    return driver.executeScript(
      `return document.readyState === "complete" &&
         !document.documentElement.hasAttribute("data-old") &&
         (!location.pathname.endsWith("options.html") ||
          document.documentElement.hasAttribute("data-loaded"))`
    );
  });
}

// Preferences save on every keystroke, so reload the page until the stored
// value matches rather than trusting the first "Saved" message.
async function waitForSavedPreference(name, expected) {
  await waitFor(`${name} to be saved`, async () => {
    await openPage("options.html");
    const field = await driver.findElement(By.name(name));
    return (await field.getAttribute("value")) === expected;
  });
}

async function screenLines() {
  const text = await driver.executeScript(
    "return document.querySelector('.xterm-rows')?.innerText ?? ''"
  );
  return text.split("\n");
}

async function openTerminal() {
  await openPage("tmux.html");
  // The tab title names the session once the host is ready, and tmux's
  // status bar appears once the session is up.
  return waitFor("tmux to start", async () => {
    const session = (await driver.getTitle()).match(/^tmux — (\S+)$/)?.[1];
    const lines = await screenLines();
    return session && lines.some(l => l.includes("[foxmux-")) && session;
  });
}

async function run(command) {
  const input = await driver.findElement(By.css(".xterm-helper-textarea"));
  await input.sendKeys(command, Key.ENTER);
}

function killSession(name) {
  try {
    execFileSync("tmux", ["kill-session", "-t", `=${name}`], {
      stdio: "ignore",
    });
  } catch {
    // Already gone.
  }
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
  const { version } = JSON.parse(readFileSync("extension/manifest.json"));
  const xpi = resolve("dist", `foxmux-${version}.xpi`);
  assert.ok(existsSync(xpi), "run `npm run build` first");

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
  await driver.installAddon(xpi, true);
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
    await waitForSavedPreference("startDir", dir);

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
    await waitForSavedPreference("startDir", "~");
    rmSync(dir, { recursive: true, force: true });
  }
});

test("closing the tab ends its tmux session", async () => {
  const session = await openTerminal();
  assert.ok(sessionExists(session), `${session} should be running`);
  await driver.get("about:blank");
  await waitFor("session to end", () => !sessionExists(session));
});

test("pressing Enter after tmux exits starts it again", async () => {
  await openTerminal();
  await run("exit");
  await waitFor("exit notice", async () =>
    (await screenLines()).some(l => l.includes("tmux exited"))
  );
  await run("");
  await waitFor("tmux to restart", async () => {
    const lines = await screenLines();
    return (
      lines.some(l => l.includes("[foxmux-")) &&
      !lines.some(l => l.includes("tmux exited"))
    );
  });
});

test("shared mode attaches to a named session that outlives the tab", async () => {
  const name = `foxmux-e2e-${process.pid}`;
  try {
    await openPage("options.html");
    await driver.findElement(By.css("input[value=shared]")).click();
    const field = await driver.findElement(By.name("sessionName"));
    await field.clear();
    await field.sendKeys(name);
    await waitForSavedPreference("sessionName", name);

    assert.equal(await openTerminal(), name);
    await driver.get("about:blank");
    await sleep(1000);
    assert.ok(sessionExists(name), "shared session should survive the tab");
  } finally {
    await openPage("options.html");
    await driver.findElement(By.css("input[value=per-tab]")).click();
    await waitFor("per-tab mode to be saved", async () => {
      await openPage("options.html");
      return driver.findElement(By.css("input[value=per-tab]")).isSelected();
    });
    killSession(name);
  }
});

test("the preferences page is localised", async () => {
  await openPage("options.html");
  const legend = await driver.findElement(By.css("legend")).getText();
  assert.equal(legend, "Sessions");
  const link = await driver.findElement(By.css("a.button")).getText();
  assert.equal(link, "Report an issue");
});
