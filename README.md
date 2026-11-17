# pr bootstrap

Start work on a Jira ticket in one command: create the branch, an empty commit and a draft PR.

```bash
pr-bootstrap OCPSG-1548
```

1. Fetches the ticket's summary and description from Jira.
2. Asks for the commit subject (Enter uses the summary) and offers branch names such as
   `OCPSG-1548-fix-the-thing`.
3. Creates the branch from `--base` (default `dev`) with an empty commit, and pushes it.
4. Opens a draft PR whose body links the ticket, holds the rendered Jira description under
   **Context**, leaves a **Changes** section to fill in, and ends with the repo's PR template.
5. Amends the commit with the PR number through
   [git-recommit](https://github.com/guardicode/git-recommit), so if a `commit-msg` hook rejects
   the message you can fix it in your editor and retry.

Options: `--base`, `--branch`, `--title`, `--skip-pr` and `--dry-run` (prints every step,
including the PR body, without touching git or GitHub). See `pr-bootstrap --help`.

## Installation

Requires [git-recommit](https://github.com/guardicode/git-recommit) and an authenticated
[GitHub CLI](https://cli.github.com) (`gh auth login`).

```bash
pipx install git+https://github.com/guardicode/git-recommit
pipx install git+https://github.com/guardicode/pr-bootstrap
```

Set these in your shell profile:

```bash
export JIRA_URL="https://your-domain.atlassian.net"
export JIRA_EMAIL="your.email@domain.com"
export JIRA_API_TOKEN="your-jira-api-token"
```

## Development setup

Install [pre-commit](https://pre-commit.com) once per machine, then enable the hooks in each clone:

```bash
pipx install pre-commit   # or: brew install pre-commit
pre-commit install        # installs the pre-commit, prepare-commit-msg and commit-msg hooks
```

If `pre-commit install` refuses because `core.hooksPath` is set (e.g. by the old commit-guard tool),
remove the global hook path first:

```bash
git config --global --unset core.hooksPath
```

## Commit messages

Commit messages follow [How to Write a Git Commit Message](https://cbea.ms/git-commit), as far as
a linter can check:

- Separate the subject from the body with a blank line.
- Keep the subject at most 72 characters long.
- Capitalize the subject.
- Don't end the subject with a period.
- Use the imperative mood in the subject (`Add`, not `Added` or `Adds`).
- Wrap the body at 72 characters.

```text
Add map writer

Explain what changed and why, not how.
```

Fixups, squashes, amends and `git revert` commits are not checked. Neither are merges. The rules come
from [gitlint-commit-hook](https://github.com/adamdelman/gitlint-commit-hook).
