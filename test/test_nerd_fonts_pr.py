# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for scripts/nerd-fonts-pr.sh, using a fake `gh` and `git push`.

Each test describes how GitHub behaves (an open pull request already exists,
workflows may not open pull requests, ...) and checks what the script asked
GitHub to do.
"""

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAKE_GH = textwrap.dedent(
    """\
    #!/bin/sh
    # Records each call; answers from the scenario in $FAKE_GITHUB.
    echo "gh $*" >> "$CALLS"
    scenario=$(cat "$FAKE_GITHUB")
    field() {
      printf '%s' "$scenario" |
        python3 -c "import json,sys; print(json.load(sys.stdin).get('$1', ''))"
    }
    case "$1 $2" in
      "pr list")
        case "$*" in
          *--head*) field open_for_branch ;;
          *) field other_open_prs ;;
        esac ;;
      "pr create")
        if [ "$(field create_error)" ]; then field create_error >&2; exit 1; fi ;;
      "run list")
        case "$*" in
          *ci.yml*) field ci_runs ;; # CI runs that have started
          *) field held_run ;; # runs waiting for approval
        esac ;;
      "api -X")
        if [ "$(field approve_error)" ]; then field approve_error >&2; exit 1; fi ;;
      "issue list")
        case "$*" in
          *length*) field open_issues ;;
          *) field open_issue_numbers ;;
        esac ;;
    esac
    exit 0
    """
)

# Passes everything to the real git except push, which is only recorded.
FAKE_GIT = textwrap.dedent(
    """\
    #!/bin/sh
    if [ "$1" = push ]; then echo "git $*" >> "$CALLS"; exit 0; fi
    exec "$REAL_GIT" "$@"
    """
)


class NerdFontsPullRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        for script in ("nerd-fonts-pr.sh", "retry.sh"):
            shutil.copy(ROOT / "scripts" / script, self.repo / "scripts")
        for path in ("extension/fonts/font.woff2", "licenses/x.txt", "NOTICE.md"):
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text("old")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        # The update script has already changed the font when this runs.
        (self.repo / "extension/fonts/font.woff2").write_text("new")

        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for name, body in (("gh", FAKE_GH), ("git", FAKE_GIT)):
            (bin_dir / name).write_text(body)
            (bin_dir / name).chmod(0o755)
        self.calls = self.tmp / "calls"
        self.calls.touch()
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "REAL_GIT": shutil.which("git"),
            "CALLS": str(self.calls),
            "FAKE_GITHUB": str(self.tmp / "github.json"),
            "GH_TOKEN": "token",
            "GITHUB_REPOSITORY": "owner/foxmux",
            "GITHUB_REPOSITORY_OWNER": "owner",
            "RUNNER_TEMP": str(self.tmp),
            "VERSION": "3.5.1",
            "REVIEW": "false",
            "CI_WAIT_ATTEMPTS": "1",
        }

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True)

    def run_script(self, github=None, **env):
        (self.tmp / "github.json").write_text(
            json.dumps(
                {
                    "open_for_branch": "0",
                    "open_issues": "0",
                    "held_run": "123",  # GitHub holds CI for approval
                    "ci_runs": "1",
                    **(github or {}),
                }
            )
        )
        result = subprocess.run(
            ["sh", "scripts/nerd-fonts-pr.sh"],
            cwd=self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
        )
        return result, self.calls.read_text().splitlines()

    def test_opens_a_pull_request_approves_ci_and_auto_merges(self):
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c.startswith("git push --force") for c in calls))
        self.assertTrue(
            any("refs/heads/automation/nerd-fonts-3.5.1" in c for c in calls)
        )
        self.assertIn(
            "gh api -X POST repos/owner/foxmux/actions/runs/123/approve", calls
        )
        self.assertIn("gh pr merge automation/nerd-fonts-3.5.1 --auto --squash", calls)

    def test_asks_for_review_when_licences_changed(self):
        result, calls = self.run_script(REVIEW="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c.startswith("gh pr merge") for c in calls))
        self.assertIn(
            "gh pr edit automation/nerd-fonts-3.5.1 --add-reviewer owner", calls
        )

    def test_does_nothing_when_the_pull_request_is_already_open(self):
        result, calls = self.run_script({"open_for_branch": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c.startswith("git push") for c in calls))
        self.assertFalse(any(c.startswith("gh pr create") for c in calls))

    def test_closes_pull_requests_for_older_versions(self):
        result, calls = self.run_script({"other_open_prs": "7"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            any(c.startswith("gh pr close 7 --delete-branch") for c in calls)
        )

    def test_falls_back_to_an_issue_when_workflows_may_not_open_pull_requests(self):
        error = (
            "pull request create failed: GraphQL: GitHub Actions is not "
            "permitted to create or approve pull requests (createPullRequest)"
        )
        result, calls = self.run_script({"create_error": error})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c.startswith("gh issue create") for c in calls))
        self.assertFalse(any(c.startswith("gh api -X POST") for c in calls))

    def test_does_not_duplicate_the_fallback_issue(self):
        error = "GitHub Actions is not permitted to create or approve pull requests"
        result, calls = self.run_script({"create_error": error, "open_issues": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c.startswith("gh issue create") for c in calls))

    def test_closes_an_earlier_fallback_issue_once_the_pull_request_opens(self):
        result, calls = self.run_script({"open_issue_numbers": "5"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c.startswith("gh issue close 5") for c in calls))

    def test_approves_every_held_run_on_the_branch(self):
        # CI and the Dependabot auto-merge workflow are both held.
        result, calls = self.run_script({"held_run": "123\n456"})
        self.assertEqual(result.returncode, 0, result.stderr)
        for run in ("123", "456"):
            self.assertIn(
                f"gh api -X POST repos/owner/foxmux/actions/runs/{run}/approve", calls
            )

    def test_does_not_approve_when_ci_already_started(self):
        result, calls = self.run_script({"held_run": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c.startswith("gh api -X POST") for c in calls))
        self.assertIn("gh pr merge automation/nerd-fonts-3.5.1 --auto --squash", calls)

    def assert_asked_for_help(self, github):
        result, calls = self.run_script(github)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c.startswith("gh pr comment") for c in calls))
        self.assertIn(
            "gh pr edit automation/nerd-fonts-3.5.1 --add-reviewer owner", calls
        )

    def test_asks_for_help_when_approval_fails(self):
        self.assert_asked_for_help({"approve_error": "HTTP 403"})

    def test_asks_for_help_when_ci_never_appears(self):
        self.assert_asked_for_help({"held_run": "", "ci_runs": "0"})

    def test_other_errors_fail_loudly(self):
        result, _ = self.run_script({"create_error": "HTTP 502: Bad Gateway"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Bad Gateway", result.stderr)


if __name__ == "__main__":
    unittest.main()
