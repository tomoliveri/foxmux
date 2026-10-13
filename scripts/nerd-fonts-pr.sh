#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Opens the pull request for a font update made by update_nerd_fonts.py,
# approves the CI run GitHub holds on it and enables auto-merge. Safe to run again: it reuses or
# repairs whatever an earlier, interrupted run left behind, and closes pull
# requests for older font versions.
#
# Needs GH_TOKEN, GITHUB_REPOSITORY, VERSION and REVIEW (true when the
# font's licences changed and a person should look before merging).

set -eu
cd "$(dirname "$0")/.."

branch="automation/nerd-fonts-$VERSION"
title="Update bundled Nerd Fonts symbols font to $VERSION"
blocked_title="Nerd Fonts $VERSION update is ready but needs a pull request"

# Older font updates that never merged are now out of date.
gh pr list --state open --json number,headRefName \
  --jq ".[] | select(.headRefName | startswith(\"automation/nerd-fonts-\")) | select(.headRefName != \"$branch\") | .number" |
  while read -r number; do
    gh pr close "$number" --delete-branch --comment "Superseded by the update to $VERSION."
  done

if [ "$(gh pr list --state open --head "$branch" --json number --jq length)" != 0 ]; then
  echo "A pull request for $VERSION is already open."
  exit 0
fi

# (Re)create the branch from this run's changes. Forcing replaces anything an
# interrupted earlier run pushed.
git switch -c "$branch"
git add extension/fonts licenses NOTICE.md
git -c user.name="github-actions[bot]" \
  -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
  commit -q -m "$title"
scripts/retry.sh git push --force \
  "https://x-access-token:$GH_TOKEN@github.com/$GITHUB_REPOSITORY.git" "HEAD:refs/heads/$branch"

{
  echo "Updates the bundled Nerd Fonts symbols font to [$VERSION](https://github.com/ryanoasis/nerd-fonts/releases/tag/v$VERSION)."
  echo
  echo "- Download checked against the SHA-256 digest GitHub records for the release."
  echo "- Repackaged as WOFF2 by \`scripts/woff2.py\`, which verified every glyph, name and the character map are unchanged."
  echo "- Licence files and NOTICE.md refreshed from the same release."
  echo
  if [ "$REVIEW" = true ]; then
    echo "**The licences that apply to the font changed. Please review \`licenses/nerd-fonts-symbols/\` before merging.**"
  else
    echo "The licences that apply to the font are unchanged, so this merges automatically once CI passes."
  fi
} > "${RUNNER_TEMP:-/tmp}/pr-body.md"

if ! gh pr create --base main --head "$branch" --title "$title" \
  --body-file "${RUNNER_TEMP:-/tmp}/pr-body.md" 2> "${RUNNER_TEMP:-/tmp}/pr-error"; then
  cat "${RUNNER_TEMP:-/tmp}/pr-error" >&2
  if ! grep -q "not permitted to create" "${RUNNER_TEMP:-/tmp}/pr-error"; then
    exit 1
  fi
  # The repository doesn't let workflows open pull requests. The update is
  # ready on its branch, so ask a person to open it rather than failing.
  echo "::warning::Pull requests from workflows are disabled for this repository; opened an issue instead."
  if [ "$(gh issue list --state open --search "\"$blocked_title\" in:title" --json number --jq length)" = 0 ]; then
    gh issue create --title "$blocked_title" --body "The update is ready on [\`$branch\`](https://github.com/$GITHUB_REPOSITORY/tree/$branch).

[**Open the pull request**](https://github.com/$GITHUB_REPOSITORY/compare/main...$branch?expand=1), then run CI on it from the Actions tab (CI → Run workflow → branch \`$branch\`).

To let the weekly run do this itself, turn on *Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests*."
  fi
  exit 0
fi

# GitHub holds every workflow run on a pull request a workflow opened until
# someone approves it, and only CI's pull_request run counts for the merge
# check. Approve the held runs on this branch, then wait for CI to start.
approved=false
failed=false
attempt=0
while [ "$attempt" -lt "${CI_WAIT_ATTEMPTS:-30}" ]; do
  for held in $(gh run list --branch "$branch" --event pull_request \
    --json databaseId,conclusion \
    --jq '.[] | select(.conclusion == "action_required") | .databaseId'); do
    gh api -X POST "repos/$GITHUB_REPOSITORY/actions/runs/$held/approve" >/dev/null || failed=true
  done
  if [ "$failed" = true ]; then
    break
  fi
  started=$(gh run list --branch "$branch" --workflow ci.yml --event pull_request \
    --json conclusion --jq '[.[] | select(.conclusion != "action_required")] | length')
  if [ "$started" != 0 ]; then
    approved=true
    break
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -lt "${CI_WAIT_ATTEMPTS:-30}" ]; then sleep 10; fi
done

if [ "$approved" != true ]; then
  echo "::warning::Could not start CI on the font pull request; asked for review."
  gh pr comment "$branch" --body "CI didn't start on its own. Open the **Checks** tab and click **Approve and run workflows**; this pull request merges once CI passes."
  gh pr edit "$branch" --add-reviewer "$GITHUB_REPOSITORY_OWNER"
elif [ "$REVIEW" = true ]; then
  gh pr edit "$branch" --add-reviewer "$GITHUB_REPOSITORY_OWNER"
fi
if [ "$REVIEW" != true ]; then
  gh pr merge "$branch" --auto --squash
fi

# A blocked attempt from an earlier week is resolved now.
gh issue list --state open --search "\"$blocked_title\" in:title" --json number --jq '.[].number' |
  while read -r number; do
    gh issue close "$number" --comment "Pull request opened automatically."
  done
