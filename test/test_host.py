# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the native host. Run with: python3 -m unittest discover test

The integration tests start the real host and talk to it the way Firefox
does, so they need tmux. They only touch tmux sessions they create.
"""

import base64
import json
import os
import secrets
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

# Generous: CI machines can be slow, and waits end as soon as they succeed.
TIMEOUT = 30

HOST = Path(__file__).resolve().parent.parent / "native" / "foxmux_host.py"
sys.path.insert(0, str(HOST.parent))

import foxmux_host as host  # noqa: E402


def setUpModule():
    # Run every test against a private tmux server, started fresh, so tests
    # never touch the user's own sessions and behave the same as on CI.
    # (The system temp dir keeps the socket path within Unix's length limit.)
    global TMUX_TMPDIR
    TMUX_TMPDIR = tempfile.mkdtemp(prefix="foxmux-tmux-")
    os.environ["TMUX_TMPDIR"] = TMUX_TMPDIR


def tearDownModule():
    subprocess.run(["tmux", "kill-server"], stderr=subprocess.DEVNULL)
    shutil.rmtree(TMUX_TMPDIR, ignore_errors=True)
    del os.environ["TMUX_TMPDIR"]


def frame(message):
    data = json.dumps(message).encode() if isinstance(message, dict) else message
    return struct.pack("=I", len(data)) + data


class HelperTests(unittest.TestCase):
    def test_session_name_keeps_safe_characters(self):
        self.assertEqual(host.session_name("my-session_1"), "my-session_1")

    def test_session_name_replaces_tmux_separators(self):
        self.assertEqual(host.session_name("a:b.c d"), "a_b_c_d")

    def test_session_name_is_limited_to_64_characters(self):
        self.assertEqual(len(host.session_name("x" * 200)), 64)

    def test_session_name_defaults_to_random_name(self):
        for requested in ("", None, 42):
            self.assertRegex(host.session_name(requested), r"^foxmux-[0-9a-f]{6}$")

    def test_start_directory_expands_home(self):
        self.assertEqual(host.start_directory("~"), (str(Path.home()), None))

    def test_start_directory_falls_back_to_home(self):
        self.assertEqual(
            host.start_directory("/no/such/dir"), (str(Path.home()), "/no/such/dir")
        )

    def test_start_directory_ignores_empty_and_non_text(self):
        for requested in ("", "  ", None, ["/usr"]):
            self.assertEqual(host.start_directory(requested), (str(Path.home()), None))

    def test_start_server_leaves_private_sockets_to_tmux(self):
        with mock.patch.object(host.subprocess, "run") as run:
            host.start_server("tmux", {"TMUX_TMPDIR": TMUX_TMPDIR})
        run.assert_not_called()

    def test_start_server_falls_back_when_the_agent_is_missing(self):
        results = iter([1, 113])  # no server, then launchctl: no such agent
        with (
            mock.patch.object(host.sys, "platform", "darwin"),
            mock.patch.object(
                host.subprocess,
                "run",
                side_effect=lambda *a, **k: mock.Mock(returncode=next(results)),
            ) as run,
        ):
            host.start_server("tmux", {})
        self.assertEqual(run.call_count, 2)

    def test_serve_waits_for_an_older_server_to_exit(self):
        results = iter([0, 0, 1])
        with (
            mock.patch.object(
                host.subprocess,
                "run",
                side_effect=lambda *a, **k: mock.Mock(returncode=next(results)),
            ),
            mock.patch.object(host.time, "sleep") as sleep,
            mock.patch.object(host.os, "execve") as execve,
        ):
            host.serve("/bin/tmux", {})
        self.assertEqual(sleep.call_count, 2)
        execve.assert_called_once_with("/bin/tmux", ["/bin/tmux", "-u", "-D"], {})

    def test_clamp_rejects_bad_numbers(self):
        self.assertEqual(host.clamp("abc", 80, 1, 1000), 80)
        self.assertEqual(host.clamp(None, 24, 1, 1000), 24)
        self.assertEqual(host.clamp(-5, 80, 1, 1000), 1)
        self.assertEqual(host.clamp(10**9, 80, 1, 1000), 1000)


class MessageReaderTests(unittest.TestCase):
    def setUp(self):
        self.read_fd, self.write_fd = os.pipe()
        self.reader = host.MessageReader(self.read_fd)
        self.sent = []
        patcher = mock.patch.object(host, "send", self.sent.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        os.close(self.read_fd)
        try:
            os.close(self.write_fd)
        except OSError:
            pass

    def test_reads_several_messages_from_one_chunk(self):
        os.write(self.write_fd, frame({"type": "a"}) + frame({"type": "b"}))
        self.assertEqual(self.reader.next(), {"type": "a"})
        self.assertEqual(self.reader.next(), {"type": "b"})

    def test_waits_for_a_message_split_across_reads(self):
        data = frame({"type": "split"})
        os.write(self.write_fd, data[:3])
        self.reader.fill()
        self.assertEqual(self.reader.queue, [])
        os.write(self.write_fd, data[3:])
        self.assertEqual(self.reader.next(), {"type": "split"})

    def test_skips_malformed_messages(self):
        os.write(self.write_fd, frame(b"{not json") + frame(b"[1, 2]"))
        os.write(self.write_fd, frame({"type": "ok"}))
        self.assertEqual(self.reader.next(), {"type": "ok"})
        self.assertEqual([m["code"] for m in self.sent], ["badMessage"] * 2)

    def test_rejects_oversized_messages(self):
        os.write(self.write_fd, struct.pack("=I", host.MAX_MESSAGE + 1))
        with self.assertRaises(host.ProtocolError):
            self.reader.fill()

    def test_end_of_input_means_the_tab_closed(self):
        os.close(self.write_fd)
        with self.assertRaises(host.TabClosed):
            self.reader.next()


@unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
class HostProcessTests(unittest.TestCase):
    """Runs the host as Firefox would and drives it over its pipes."""

    def setUp(self):
        self.unread = {}  # bytes read past the last message, per host

    def start_host(self, *, code=None):
        args = [sys.executable, str(HOST)]
        if code:
            args = [sys.executable, "-c", code]
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(Path.home()),
                "TMUX_TMPDIR": os.environ["TMUX_TMPDIR"],
            },
            cwd=HOST.parent,
        )
        self.addCleanup(self.stop_host, process)
        return process

    def stop_host(self, process):
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        process.wait(timeout=TIMEOUT)
        process.stdout.close()

    def send(self, process, message):
        process.stdin.write(frame(message))
        process.stdin.flush()

    def receive(self, process, until, timeout=TIMEOUT):
        """Collect messages until until(messages) is true.

        Reads the pipe directly with our own buffer: select() can't see data
        already held in Python's buffered reader, so mixing the two loses
        messages that arrive in the same write.
        """
        buffer = self.unread.pop(process.pid, b"")
        messages = []
        deadline = time.monotonic() + timeout
        while not until(messages):
            if len(buffer) >= 4:
                (length,) = struct.unpack("=I", buffer[:4])
                if len(buffer) >= 4 + length:
                    messages.append(json.loads(buffer[4 : 4 + length]))
                    buffer = buffer[4 + length :]
                    continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.fail(f"timed out; got {messages}")
            fd = process.stdout.fileno()
            if not select.select([fd], [], [], remaining)[0]:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            buffer += chunk
        self.unread[process.pid] = buffer
        return messages

    def screen(self, messages):
        return b"".join(
            base64.b64decode(m["data"]) for m in messages if m["type"] == "output"
        ).decode(errors="replace")

    def wait_for_text(self, process, text):
        return self.receive(process, lambda ms: text in self.screen(ms))

    def ready(self, process, **request):
        self.send(process, {"type": "open", "cols": 100, "rows": 30, **request})
        messages = self.receive(
            process, lambda ms: any(m["type"] == "ready" for m in ms)
        )
        return next(m for m in messages if m["type"] == "ready"), messages

    def session_exists(self, name):
        return (
            subprocess.run(
                ["tmux", "has-session", "-t", "=" + name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )

    def wait_until(self, condition, timeout=TIMEOUT):
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                self.fail("condition not met in time")
            time.sleep(0.1)

    def unique_session(self):
        name = "foxmux-test-" + secrets.token_hex(3)
        self.addCleanup(
            subprocess.run,
            ["tmux", "kill-session", "-t", "=" + name],
            stderr=subprocess.DEVNULL,
        )
        return name

    def test_runs_commands_in_the_start_directory(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            process = self.start_host()
            ready, _ = self.ready(process, cwd=directory)
            self.assertEqual(ready["protocol"], host.PROTOCOL)
            self.send(process, {"type": "input", "data": "pwd; echo $((6*7))x\r"})
            screen = self.screen(self.wait_for_text(process, "42x"))
            self.assertIn(directory, screen)

    def test_missing_start_directory_falls_back_with_a_notice(self):
        process = self.start_host()
        _, messages = self.ready(process, cwd="/no/such/dir")
        messages += self.receive(
            process, lambda ms: any(m["type"] == "notice" for m in messages + ms)
        )
        notice = next(m for m in messages if m["type"] == "notice")
        self.assertEqual(notice["code"], "startDirMissing")
        self.assertEqual(notice["args"], ["/no/such/dir", str(Path.home())])

    def test_closing_the_tab_ends_a_per_tab_session(self):
        process = self.start_host()
        ready, _ = self.ready(process)
        session = ready["session"]
        self.wait_until(lambda: self.session_exists(session))
        process.stdin.close()
        process.wait(timeout=TIMEOUT)
        self.assertFalse(self.session_exists(session))

    def test_closing_the_tab_after_detaching_still_ends_the_session(self):
        process = self.start_host()
        ready, _ = self.ready(process)
        session = ready["session"]
        self.send(process, {"type": "input", "data": "tmux detach-client\r"})
        self.receive(process, lambda ms: any(m["type"] == "exit" for m in ms))
        self.assertTrue(self.session_exists(session), "detached, not ended")
        process.stdin.close()
        process.wait(timeout=TIMEOUT)
        self.assertFalse(self.session_exists(session))

    def test_reconnecting_reattaches_to_the_same_session(self):
        process = self.start_host()
        first, _ = self.ready(process)
        self.send(process, {"type": "input", "data": "tmux detach-client\r"})
        self.receive(process, lambda ms: any(m["type"] == "exit" for m in ms))
        second, _ = self.ready(process)
        self.assertEqual(first["session"], second["session"])

    def test_shared_sessions_survive_the_tab(self):
        name = self.unique_session()
        process = self.start_host()
        ready, _ = self.ready(process, session=name, persist=True)
        self.assertEqual(ready["session"], name)
        self.wait_until(lambda: self.session_exists(name))
        process.stdin.close()
        process.wait(timeout=TIMEOUT)
        self.assertTrue(self.session_exists(name))

    def test_survives_malformed_and_odd_messages(self):
        process = self.start_host()
        self.ready(process)
        process.stdin.write(frame(b"{not json"))
        for message in (
            {"type": "resize", "cols": "wide", "rows": None},
            {"type": "input", "data": 42},
            {"type": "input", "data": "€", "binary": True},
            {"type": "mystery"},
        ):
            self.send(process, message)
        self.send(process, {"type": "input", "data": "echo still-$((1+1))\r"})
        messages = self.wait_for_text(process, "still-2")
        self.assertIn("badMessage", [m.get("code") for m in messages])
        self.assertIsNone(process.poll())

    def test_oversized_message_stops_the_host_with_an_error(self):
        process = self.start_host()
        process.stdin.write(struct.pack("=I", host.MAX_MESSAGE + 1))
        process.stdin.flush()
        messages = self.receive(process, lambda ms: bool(ms))
        self.assertEqual(messages[0]["code"], "protocolError")
        self.assertEqual(process.wait(timeout=TIMEOUT), 0)

    def test_reports_the_exit_code_of_tmux(self):
        fake_tmux = Path(tempfile.mkdtemp()) / "tmux"
        self.addCleanup(shutil.rmtree, fake_tmux.parent)
        fake_tmux.write_text("#!/bin/sh\necho bye\nexit 3\n")
        fake_tmux.chmod(0o755)
        process = self.start_host(
            code="import foxmux_host as h; "
            f"h.find_tmux = lambda env: {str(fake_tmux)!r}; h.main()"
        )
        self.send(process, {"type": "open"})
        messages = self.receive(
            process, lambda ms: any(m["type"] == "exit" for m in ms)
        )
        self.assertIn({"type": "exit", "code": 3}, messages)
        self.assertIn("bye", self.screen(messages))

    def test_receive_sees_messages_that_arrive_together(self):
        # Regression test for this file's own helper: two messages in one
        # write used to leave the second stuck in a buffer select() can't see.
        writer = (
            "import json, struct, sys, time\n"
            "def frame(m):\n"
            "    d = json.dumps(m).encode()\n"
            "    return struct.pack('=I', len(d)) + d\n"
            "sys.stdout.buffer.write(frame({'type': 'output', 'data': ''})"
            " + frame({'type': 'exit', 'code': 0}))\n"
            "sys.stdout.flush()\n"
            "time.sleep(10)\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", writer],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        messages = self.receive(
            process, lambda ms: any(m["type"] == "exit" for m in ms), timeout=5
        )
        self.assertEqual([m["type"] for m in messages], ["output", "exit"])

    def test_reports_missing_tmux(self):
        process = self.start_host(
            code="import foxmux_host as h; h.find_tmux = lambda env: None; h.main()"
        )
        self.send(process, {"type": "open"})
        messages = self.receive(process, lambda ms: bool(ms))
        self.assertEqual(
            messages[0], {"type": "error", "code": "tmuxMissing", "args": []}
        )


if __name__ == "__main__":
    unittest.main()
