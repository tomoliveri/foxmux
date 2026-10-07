# Notices

foxmux makes no copyright claim of its own and adds no licence of its own.
Its source files are offered under the **Mozilla Public License 2.0** — the
licence of Firefox, the platform it extends — and carry the MPL-2.0 Exhibit A
header. The full text is in [`LICENSE`](LICENSE).

## Software foxmux works with (not bundled)

| Project                                     | Licence | Text                                             |
| ------------------------------------------- | ------- | ------------------------------------------------ |
| [tmux](https://github.com/tmux/tmux)        | ISC     | [`licenses/tmux-ISC.txt`](licenses/tmux-ISC.txt) |
| [Firefox](https://www.mozilla.org/firefox/) | MPL-2.0 | [`LICENSE`](LICENSE)                             |

foxmux does not include, modify or redistribute any tmux or Firefox code. It
launches the tmux already installed on your system and runs as a Firefox
WebExtension. Their licences are reproduced here so that anyone redistributing
foxmux alongside them has the terms to hand.

## Software bundled in the extension

| Project                                                                                                                  | Version | Licence                                                                                              | Text                                                                   |
| ------------------------------------------------------------------------------------------------------------------------ | ------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| [xterm.js](https://github.com/xtermjs/xterm.js) (`@xterm/xterm`)                                                         | 6.0.0   | MIT                                                                                                  | [`licenses/xterm.js-MIT.txt`](licenses/xterm.js-MIT.txt)               |
| `@xterm/addon-fit`                                                                                                       | 0.11.0  | MIT                                                                                                  | [`licenses/xterm-addon-fit-MIT.txt`](licenses/xterm-addon-fit-MIT.txt) |
| [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) Symbols Only (`extension/fonts/SymbolsNerdFontMono-Regular.woff2`) | 3.4.0   | MIT; bundled icon sets under their own licences (CC BY 4.0, Apache-2.0, SIL OFL 1.1, MIT, Unlicense) | [`licenses/nerd-fonts-symbols/`](licenses/nerd-fonts-symbols/)         |

The font is the release file `SymbolsNerdFontMono-Regular.ttf` repackaged
losslessly as WOFF2 (fontTools, no added metadata): glyphs, names and all
other font data are unchanged, meeting the conditions the SIL OFL FAQ (2.2)
sets for repackaging without renaming. Its glyphs come from Codicons, Devicons,
Font Awesome, Font Awesome Extension, Font Logos, IEC Power Symbols, Material
Design Icons, Seti-UI, Octicons, Pomicons, Powerline Symbols, Powerline Extra
Symbols and Weather Icons; `license-audit.md` from Nerd Fonts lists which
licence applies to each, and the full licence texts sit beside it. Attribution
for the CC BY 4.0 icon sets (Codicons by Microsoft, Font Awesome by Fonticons,
Inc.) is given here.

The xterm.js files are copied from the npm packages pinned in
`package-lock.json` by `npm run vendor`, unmodified except that their
`sourceMappingURL` comment lines are removed because the maps are not shipped.
Copyright in them belongs to their authors as stated in their licence files.

## Trademarks

Firefox and Mozilla are trademarks of the Mozilla Foundation. tmux is the name
of the tmux project. foxmux is an independent project, not affiliated with or
endorsed by either, and claims no rights in those names.
