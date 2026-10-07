#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""foxmux native messaging host.

Firefox starts this program when a foxmux terminal tab opens, and it lives as
long as the tab. It runs tmux in a pseudo-terminal and relays bytes between
tmux and the tab. Messages in both directions are JSON, each preceded by its
length as a 32-bit native-endian integer (the WebExtensions native messaging
protocol).

From the tab:
    {"type": "open", "cwd": "~", "cols": 80, "rows": 24,
     "session": "", "persist": false}
    {"type": "input", "data": "ls\\r", "binary": false}
    {"type": "resize", "cols": 120, "rows": 40}

To the tab:
    {"type": "ready", "protocol": 1, "session": "foxmux-1a2b3c"}
    {"type": "output", "data": "<base64>"}
    {"type": "notice", "code": "startDirMissing", "args": ["~/x", "/home/me"]}
    {"type": "error", "code": "tmuxMissing", "args": []}
    {"type": "exit", "code": 0}

"code" names a message the extension translates (see extension/_locales).
After "exit" the tab may send "open" again to reattach to the same session.
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
import termios

# Bump when a change to the messages above would break the other side.
PROTOCOL = 1

# Firefox starts native hosts with a minimal PATH, so also look where package
# managers usually put tmux.
EXTRA_PATH = ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"]

# Large enough for any paste; anything bigger means the stream is corrupt.
MAX_MESSAGE = 64 * 1024 * 1024


class TabClosed(Exception):
    """Firefox closed the tab, or asked the host to stop."""


class ProtocolError(Exception):
    """The message stream from Firefox cannot be trusted any more."""


def send(message):
    data = json.dumps(message).encode("utf-8")
    data = struct.pack("=I", len(data)) + data
    while data:
        data = data[os.write(1, data) :]


def send_problem(kind, code, *args):
    send({"type": kind, "code": code, "args": [str(a) for a in args]})


class MessageReader:
    """Reads length-prefixed JSON messages from Firefox (stdin by default)."""

    def __init__(self, fd=0):
        self.fd = fd
        self.buffer = b""
        self.queue = []

    def fill(self):
        """Read what is available and queue every complete message."""
        chunk = os.read(self.fd, 65536)
        if not chunk:
            raise TabClosed
        self.buffer += chunk
        while len(self.buffer) >= 4:
            (length,) = struct.unpack("=I", self.buffer[:4])
            if length > MAX_MESSAGE:
                raise ProtocolError(f"message of {length} bytes")
            if len(self.buffer) < 4 + length:
                break
            body = self.buffer[4 : 4 + length]
            self.buffer = self.buffer[4 + length :]
            try:
                message = json.loads(body)
            except ValueError:
                message = None
            if isinstance(message, dict):
                self.queue.append(message)
            else:
                send_problem("notice", "badMessage")

    def next(self):
        """Wait for the next message."""
        while not self.queue:
            self.fill()
        return self.queue.pop(0)


def clamp(value, default, low, high):
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return default


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


def find_tmux(env):
    return shutil.which("tmux", path=env["PATH"])


def start_directory(requested):
    """Return (directory, problem), falling back to home if needed."""
    if not isinstance(requested, str) or not requested.strip():
        requested = "~"
    path = os.path.expanduser(os.path.expandvars(requested))
    if os.path.isdir(path):
        return os.path.abspath(path), None
    return os.path.expanduser("~"), requested


def session_name(requested):
    # Keep to characters tmux never treats specially in target names.
    if not isinstance(requested, str):
        requested = ""
    name = re.sub(r"[^A-Za-z0-9_-]", "_", requested)[:64]
    return name or "foxmux-" + secrets.token_hex(3)


def set_window_size(fd, cols, rows):
    cols = clamp(cols, 80, 1, 1000)
    rows = clamp(rows, 24, 1, 1000)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def write_input(fd, message):
    data = message.get("data")
    if not isinstance(data, str):
        return
    # xterm.js reports some mouse events as raw bytes, one character each.
    try:
        data = data.encode("latin-1" if message.get("binary") else "utf-8")
    except UnicodeEncodeError:
        return
    while data:
        data = data[os.write(fd, data) :]


def attach(tmux, env, session, request, reader):
    """Run a tmux client for one "open" request; return its exit code.

    Raises TabClosed if the tab closes while tmux is running.
    """
    cwd, missing = start_directory(request.get("cwd"))
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(  # noqa: S606 - exec tmux directly, no shell
            tmux, [tmux, "-u", "new-session", "-A", "-s", session, "-c", cwd], env
        )

    try:
        set_window_size(fd, request.get("cols"), request.get("rows"))
        send({"type": "ready", "protocol": PROTOCOL, "session": session})
        if missing:
            send_problem("notice", "startDirMissing", missing, cwd)

        while True:
            while reader.queue:
                message = reader.queue.pop(0)
                if message.get("type") == "input":
                    write_input(fd, message)
                elif message.get("type") == "resize":
                    set_window_size(fd, message.get("cols"), message.get("rows"))

            readable, _, _ = select.select([reader.fd, fd], [], [])
            if fd in readable:
                try:
                    output = os.read(fd, 32768)
                except OSError:  # EIO: tmux has exited
                    output = b""
                if not output:
                    break
                send({"type": "output", "data": base64.b64encode(output).decode()})
            if reader.fd in readable:
                reader.fill()
    finally:
        os.close(fd)
        try:
            os.kill(pid, signal.SIGHUP)  # detaches if tmux is still running
        except ProcessLookupError:
            pass
        _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


def kill_session(tmux, env, session):
    subprocess.run(
        [tmux, "kill-session", "-t", "=" + session],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    def stop(signum, frame):
        raise TabClosed

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)

    reader = MessageReader()
    env = tmux_environment()
    tmux = find_tmux(env)
    session = None
    persist = False
    try:
        while True:
            request = reader.next()
            if request.get("type") != "open":
                continue
            if not tmux:
                send_problem("error", "tmuxMissing")
                return
            if session is None:
                session = session_name(request.get("session"))
                persist = bool(request.get("persist"))
            code = attach(tmux, env, session, request, reader)
            send({"type": "exit", "code": code})
    except TabClosed:
        pass
    except ProtocolError:
        send_problem("error", "protocolError")
    finally:
        # A per-tab session ends with its tab, even if tmux was detached.
        # A shared session is left running.
        if session and not persist:
            kill_session(tmux, env, session)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
