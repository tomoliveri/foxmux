# foxmux

[![CI](https://github.com/tomoliveri/foxmux/actions/workflows/ci.yml/badge.svg)](https://github.com/tomoliveri/foxmux/actions/workflows/ci.yml)
[![Compatibility](https://github.com/tomoliveri/foxmux/actions/workflows/compat.yml/badge.svg)](https://github.com/tomoliveri/foxmux/actions/workflows/compat.yml)

A Firefox extension that opens a real [tmux](https://github.com/tmux/tmux)
terminal in a browser tab.

- Click the toolbar button (or press **Alt+Shift+T**) to open a terminal tab.
- Each tab runs a genuine `tmux` client in a pseudo-terminal on your machine,
  rendered with [xterm.js](https://xtermjs.org/): colours, mouse, resizing,
  copy/paste and all your tmux key bindings and config work as normal.
- Tabs start in `~` by default; change the start directory in the extension's
  settings.

## How it works

```
tmux.html (xterm.js)  ⇄  Firefox native messaging  ⇄  foxmux_host.py  ⇄  pty  ⇄  tmux
```

Browser extensions cannot start processes, so foxmux ships a small native
messaging host (`native/foxmux_host.py`, Python 3 standard library only). Firefox
launches it when a terminal tab opens; it starts `tmux new-session -A` in a
pseudo-terminal and relays bytes between tmux and the tab. Only the foxmux
extension (ID `foxmux@foxmux`) is allowed to talk to the host.

## Requirements

- Firefox 128 or newer
- tmux
- Python 3.9 or newer
- macOS or Linux

## Install

1. From the [latest release](https://github.com/tomoliveri/foxmux/releases/latest),
   open `foxmux-<version>-signed.xpi` in Firefox and click _Add_. It is signed
   by Mozilla and updates itself when new releases come out.
2. Download `foxmux-host-<version>.tar.gz` from the same release, unpack it
   and install the native host for your user:

   ```sh
   ./install.sh            # ./install.sh --uninstall to remove
   ```

   Re-run it when release notes say the native host changed.

### From source

```sh
npm ci --ignore-scripts && npm run vendor
./install.sh
```

Then open `about:debugging#/runtime/this-firefox`, choose _Load Temporary
Add-on…_ and pick `extension/manifest.json` (removed when Firefox restarts).

## Settings

Open `about:addons` → foxmux → _Preferences_:

| Setting            | Default             | Notes                                                                                                                           |
| ------------------ | ------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Start directory    | `~`                 | `~` and `$VARS` are expanded; falls back to `~` if missing                                                                      |
| Sessions           | New session per tab | Per-tab sessions are killed when the tab closes. _Shared_ mode attaches every tab to one named session that survives tab closes |
| Font size / family | 14 / Menlo…         |                                                                                                                                 |
| Option as Meta     | off                 | macOS only                                                                                                                      |

## Notes

- Firefox keeps some shortcuts for itself (e.g. **Cmd+T**, **Cmd+W**, and
  **Ctrl+Tab**). On macOS tmux's usual **Ctrl+b** prefix is unaffected.
- Icons from tools like `eza --icons`, starship and powerline prompts work out
  of the box: foxmux bundles the Nerd Fonts symbols font.
- Scrollback lives in tmux (`prefix [` or `set -g mouse on`).
- With tmux mouse mode on, hold **Option** while dragging to make a browser
  selection.
- If a tab says it cannot reach the native host, re-run `./install.sh`.

## Security

foxmux gives a browser tab the same power as a terminal window: whatever runs
in the tab runs as you. The design keeps that power away from web content:

- Only the extension ID `foxmux@foxmux` may start the native host; Firefox
  enforces this, and web pages cannot call native messaging at all.
- The terminal page is not web-accessible, so sites cannot frame or open it,
  and the extension has no content scripts and talks to no server.
- Extension pages run under Firefox's default Manifest V3 Content Security
  Policy: only the extension's own scripts can run, with no `eval` or remote
  code.
- The host never opens a network port and never uses a shell to start tmux;
  start directories and session names are passed as plain arguments.
- Terminal output is untrusted: links in it open only if they are `http` or
  `https`, in a new tab.

The remaining risks are those of any terminal: programs you run, and other
add-ons or software already running as your user. Keep the AMO signing key in
`.amo-credentials` private; anyone holding it can sign add-ons as you.

## Development

```sh
npm ci --ignore-scripts        # dependencies, pinned by package-lock.json
npm run lint                   # Prettier, ESLint (Mozilla's rules), Mozilla's add-on linter
ruff format native test && ruff check native test
npm test                       # unit tests, plus host tests against real tmux
npm run build && npm run test:e2e   # end-to-end tests in a real Firefox
```

`extension/vendor/` is generated from npm by `npm run vendor`. The host and
end-to-end tests need tmux; the end-to-end tests also need the native host
installed (`./install.sh`). Set `FIREFOX_BIN` to choose a Firefox.

User-facing text lives in `extension/_locales/`; the native host sends message
codes, not text, so everything shown in the tab can be translated.

### Automation

- **CI** lints, audits shipped dependencies and runs the end-to-end tests on
  Linux (packaged and latest tmux) and macOS for every push and pull request.
- **Compatibility** runs weekly against Firefox release, beta, nightly and ESR
  with tmux's latest release and development branch, and opens an issue if
  anything breaks. It also flags new Nerd Fonts releases.
- **Dependabot** keeps npm packages, GitHub Actions and Ruff current; patch and
  minor updates merge automatically once CI passes.
- **Release** signs a new version through addons.mozilla.org (unlisted) and
  publishes it on GitHub whenever shipped files change, then installed copies
  pick it up through `update_url`. `scripts/release-version.sh` picks the
  number: the next patch version, or the manifest's version if you raised it
  for a bigger release. The release commits that version to `main`, so each tag
  holds exactly what shipped. Signing uses the `AMO_JWT_ISSUER` and
  `AMO_JWT_SECRET` repository secrets; the version commit uses the
  `RELEASE_DEPLOY_KEY` deploy key, the only actor besides admins that may push
  to `main` without the CI check.

## Reporting issues

Use _Report an issue_ in foxmux's preferences, or open one at
<https://github.com/tomoliveri/foxmux/issues>.

## Licence

foxmux makes no copyright or licence claim of its own. Its source is offered
under the [Mozilla Public License 2.0](LICENSE), Firefox's licence. tmux's ISC
licence and the licences of the bundled xterm.js files and Nerd Fonts
symbols font are in
[`licenses/`](licenses); see [`NOTICE.md`](NOTICE.md) for details and
trademark notes.
