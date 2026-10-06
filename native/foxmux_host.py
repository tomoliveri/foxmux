#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""foxmux native messaging host.

Firefox starts this program when a foxmux terminal tab opens. It runs tmux in
a pseudo-terminal and relays bytes between tmux and the tab. Messages in both
directions are JSON, each preceded by its length as a 32-bit native-endian
integer (the WebExtensions native messaging protocol).

From the tab:
    {"type": "open", "cwd": "~", "cols": 80, "rows": 24,
     "session": "", "persist": false}
    {"type": "input", "data": "ls\\r", "binary": false}
    {"type": "resize", "cols": 120, "rows": 40}

To the tab:
    {"type": "ready", "session": "foxmux-1a2b3c"}
    {"type": "output", "data": "<base64>"}
    {"type": "notice", "message": "..."}
    {"type": "error", "message": "..."}
    {"type": "exit", "code": 0}
"""

import base64
import fcntl
import json
import os
import pty
import pwd
import re
import secrets
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios

# Firefox starts native hosts with a minimal PATH, so also look where package
# managers usually put tmux.
EXTRA_PATH = ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"]


def send(message):
    data = json.dumps(message).encode("utf-8")
    os.write(1, struct.pack("=I", len(data)))
    while data:
        data = data[os.write(1, data) :]


class MessageReader:
    """Collects length-prefixed messages from stdin without blocking."""

    def __init__(self):
        self.buffer = b""

    def read(self):
        """Return the complete messages read so far, or None once Firefox
        has closed the pipe."""
        chunk = os.read(0, 65536)
        if not chunk:
            return None
        self.buffer += chunk
        messages = []
        while len(self.buffer) >= 4:
            (length,) = struct.unpack("=I", self.buffer[:4])
            if len(self.buffer) < 4 + length:
                break
            messages.append(json.loads(self.buffer[4 : 4 + length]))
            self.buffer = self.buffer[4 + length :]
        return messages


def tmux_environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOZ_")}
    env.pop("TMUX", None)
    user = pwd.getpwuid(os.getuid())
    env.setdefault("HOME", user.pw_dir)
    env.setdefault("SHELL", user.pw_shell or "/bin/sh")
    env["PATH"] = os.pathsep.join([env.get("PATH", "/usr/bin:/bin")] + EXTRA_PATH)
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    if not (env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG")):
        env["LANG"] = "en_US.UTF-8"
    return env


def start_directory(requested):
    path = os.path.expanduser(os.path.expandvars(requested or "~"))
    if os.path.isdir(path):
        return os.path.abspath(path), None
    home = os.path.expanduser("~")
    return home, f"Start directory {requested!r} not found, using {home}"


def session_name(requested):
    # Keep to characters tmux never treats specially in target names.
    name = re.sub(r"[^A-Za-z0-9_-]", "_", requested or "")[:64]
    return name or "foxmux-" + secrets.token_hex(3)


def set_window_size(fd, cols, rows):
    cols = min(max(int(cols), 1), 1000)
    rows = min(max(int(rows), 1), 1000)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def main():
    reader = MessageReader()
    messages = []
    while not messages:
        messages = reader.read()
        if messages is None:
            return
    request = messages.pop(0)
    if request.get("type") != "open":
        send({"type": "error", "message": "Expected an open message."})
        return

    env = tmux_environment()
    tmux = shutil.which("tmux", path=env["PATH"])
    if not tmux:
        send({"type": "error", "message": "tmux is not installed."})
        return

    cwd, warning = start_directory(request.get("cwd"))
    session = session_name(request.get("session"))
    persist = bool(request.get("persist"))

    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(  # noqa: S606 - exec tmux directly, no shell
            tmux, [tmux, "-u", "new-session", "-A", "-s", session, "-c", cwd], env
        )

    set_window_size(fd, request.get("cols", 80), request.get("rows", 24))
    send({"type": "ready", "session": session})
    if warning:
        send({"type": "notice", "message": warning})

    def close_tab(*args):
        # A per-tab session goes away with its tab; a shared one stays alive
        # and we only detach from it.
        if not persist:
            subprocess.run(
                [tmux, "kill-session", "-t", "=" + session],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, close_tab)
    signal.signal(signal.SIGHUP, close_tab)

    def handle(message):
        if message.get("type") == "input":
            encoding = "latin-1" if message.get("binary") else "utf-8"
            data = message.get("data", "").encode(encoding)
            while data:
                data = data[os.write(fd, data) :]
        elif message.get("type") == "resize":
            set_window_size(fd, message.get("cols", 80), message.get("rows", 24))

    for message in messages:
        handle(message)

    while True:
        readable, _, _ = select.select([0, fd], [], [])
        if fd in readable:
            try:
                output = os.read(fd, 32768)
            except OSError:  # EIO: tmux has exited
                output = b""
            if not output:
                break
            send({"type": "output", "data": base64.b64encode(output).decode()})
        if 0 in readable:
            messages = reader.read()
            if messages is None:
                close_tab()
            for message in messages:
                handle(message)

    _, status = os.waitpid(pid, 0)
    send({"type": "exit", "code": os.waitstatus_to_exitcode(status)})


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
