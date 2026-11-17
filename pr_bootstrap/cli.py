import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import Tuple

import requests
from requests.auth import HTTPBasicAuth

COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"


def validate_prerequisites() -> None:
    missing = []
    if not shutil.which("git"):
        missing.append("git CLI")
    if not shutil.which("gh"):
        missing.append("GitHub CLI (gh)")
    if not shutil.which("git-recommit"):
        missing.append("git-recommit (pipx install git+https://github.com/guardicode/git-recommit)")

    env_vars = ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    for var in env_vars:
        if not os.environ.get(var):
            missing.append(f"Environment variable: {var}")

    if missing:
        print(
            f"{COLOR_RED}Error: Missing prerequisites. "
            f"Please install or configure the following:{COLOR_RESET}"
        )
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)

    auth_check = subprocess.run(["gh", "auth", "status"], capture_output=True)
    if auth_check.returncode != 0:
        print(
            f"{COLOR_RED}Error: GitHub CLI is not authenticated. "
            f"Run 'gh auth login' first.{COLOR_RESET}"
        )
        sys.exit(1)


def run_cmd(cmd, capture=False):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"{COLOR_RED}Command failed: {' '.join(cmd)}{COLOR_RESET}")
        if capture:
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip())
        sys.exit(1)
    return result.stdout.strip() if capture else None


def get_jira_details(ticket_id: str) -> Tuple[str, str]:
    url = f"{os.environ['JIRA_URL'].rstrip('/')}/rest/api/2/issue/{ticket_id}"
    auth = HTTPBasicAuth(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])

    try:
        # renderedFields gives the description as HTML, which GitHub renders; the raw field
        # is Jira wiki markup, which it doesn't
        params = {"fields": "summary,description", "expand": "renderedFields"}
        response = requests.get(url, auth=auth, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        summary = data["fields"].get("summary") or "No summary"
        description = ((data.get("renderedFields") or {}).get("description") or "").strip()
        return summary, description
    except requests.exceptions.RequestException as err:
        print(f"{COLOR_RED}Error fetching Jira ticket {ticket_id}: {err}{COLOR_RESET}")
        sys.exit(1)


def generate_branch_name_options(ticket_id, summary):
    clean_summary = re.sub(r"[^a-zA-Z0-9\s]", "", summary.lower())
    words = clean_summary.split()

    stop_words = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "is",
        "are",
        "to",
        "in",
        "on",
        "for",
        "with",
        "of",
        "at",
        "by",
        "from",
        "as",
        "into",
        "about",
    }
    filtered_words = [w for w in words if w not in stop_words]

    options = []
    if words:
        options.append(f"{ticket_id}-{'-'.join(words[:6])}")
    if filtered_words:
        opt2 = f"{ticket_id}-{'-'.join(filtered_words[:5])}"
        if opt2 not in options:
            options.append(opt2)
    if len(filtered_words) > 3:
        opt3 = f"{ticket_id}-{'-'.join(filtered_words[:3])}"
        if opt3 not in options:
            options.append(opt3)

    return options if options else [f"{ticket_id}-task"]


def get_repo_pr_template():
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return ""

    template_paths = [
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/pull_request_template.md",
        "PULL_REQUEST_TEMPLATE.md",
        "pull_request_template.md",
        "docs/PULL_REQUEST_TEMPLATE.md",
    ]

    for path in template_paths:
        full_path = os.path.join(git_root, path)
        if os.path.isfile(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
    return ""


# shortcut: main is one long linear script; split it into steps if it grows further
def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(description="Start a new task branch from a Jira ticket.")
    parser.add_argument("ticket", help="The Jira ticket ID (e.g., PROJ-123)")
    parser.add_argument("--base", default="dev", help="Base branch or git ref (default: dev)")
    parser.add_argument("--branch", help="Specify a custom branch name manually")
    parser.add_argument("--title", help="Specify the commit/PR title directly (bypasses prompt)")
    parser.add_argument("--skip-pr", action="store_true", help="Skip pushing and creating the PR")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print actions without executing them"
    )
    args = parser.parse_args()

    validate_prerequisites()
    ticket_id = args.ticket.upper()

    print(f"{COLOR_CYAN}Fetching details for {ticket_id}...{COLOR_RESET}")
    summary, description = get_jira_details(ticket_id)
    print(f"Jira Summary: {summary}")

    if args.title:
        commit_subject = args.title
    else:
        commit_subject = input(
            "\nEnter a short, imperative commit subject (Press Enter to use summary): "
        ).strip()
        if not commit_subject:
            commit_subject = summary

    # Truncate subject to ensure it passes gitlint-commit-hook's 72 character limit
    prefix = f"{ticket_id}: "
    if len(prefix) + len(commit_subject) > 72:
        allowed_len = 72 - len(prefix) - 3
        commit_subject = commit_subject[:allowed_len].strip() + "..."

    if not description:
        description = input(
            "\nNo description found in Jira. "
            "Enter a short description (or press Enter to leave empty): "
        ).strip()

    if args.branch:
        branch_name = args.branch
    else:
        options = generate_branch_name_options(ticket_id, commit_subject)
        print(f"\n{COLOR_CYAN}Select a branch name:{COLOR_RESET}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        print("  c. Custom branch name")

        while True:
            choice = input(f"\nEnter choice (1-{len(options)} or 'c') [1]: ").strip().lower()
            if not choice or choice == "1":
                branch_name = options[0]
                break
            elif choice == "c":
                branch_name = input("Enter custom branch name: ").strip()
                if branch_name:
                    break
            elif choice.isdigit() and 1 <= int(choice) <= len(options):
                branch_name = options[int(choice) - 1]
                break
            else:
                print(f"{COLOR_YELLOW}Invalid choice. Try again.{COLOR_RESET}")

    print(f"\n{COLOR_CYAN}Creating branch '{branch_name}' from '{args.base}'...{COLOR_RESET}")
    if args.dry_run:
        print(f"{COLOR_YELLOW}[DRY RUN] git fetch origin{COLOR_RESET}")
        print(f"{COLOR_YELLOW}[DRY RUN] git checkout -B {branch_name} {args.base}{COLOR_RESET}")
    else:
        run_cmd(["git", "fetch", "origin"], capture=True)
        run_cmd(["git", "checkout", "-B", branch_name, args.base], capture=True)

    body_placeholder = "<Replace this line with your commit description explaining WHAT and WHY>"
    commit_msg = f"{ticket_id}: {commit_subject}\n\n{body_placeholder}"

    if args.dry_run:
        # Python 3.11 doesn't allow a backslash inside an f-string expression
        one_line_msg = commit_msg.replace("\n", " ")
        print(
            f"{COLOR_YELLOW}[DRY RUN] git commit --allow-empty --no-verify -m '{one_line_msg}'"
            f"{COLOR_RESET}"
        )
    else:
        run_cmd(
            ["git", "commit", "--allow-empty", "--no-verify", "-m", commit_msg],
            capture=True,
        )

    if args.skip_pr:
        if args.dry_run:
            print(
                f"\n{COLOR_GREEN}[DRY RUN] Simulated local branch and commit. "
                f"Skipping PR creation.{COLOR_RESET}"
            )
        else:
            print(
                f"\n{COLOR_GREEN}Success: Local branch and commit created. "
                f"Skipping PR creation.{COLOR_RESET}"
            )
        print(f"  {COLOR_CYAN}Branch:{COLOR_RESET} {branch_name}")
        sys.exit(0)

    print(
        f"{COLOR_CYAN}Pushing to remote and creating Draft PR against {args.base}...{COLOR_RESET}"
    )
    if args.dry_run:
        print(
            f"{COLOR_YELLOW}[DRY RUN] git push --force-with-lease -u origin {branch_name}"
            f"{COLOR_RESET}"
        )
    else:
        run_cmd(
            ["git", "push", "--force-with-lease", "-u", "origin", branch_name],
            capture=True,
        )

    repo_template = get_repo_pr_template()
    jira_base_url = os.environ["JIRA_URL"].rstrip("/")
    pr_body = (
        f"**Jira:** [{ticket_id}: {summary}]({jira_base_url}/browse/{ticket_id})\n\n"
        f"## Context\n\n{description or '<!-- Why is this change needed? -->'}\n\n"
        "## Changes\n\n<!-- What does this PR change, and how? -->\n\n"
        f"{repo_template}"
    )

    if args.dry_run:
        pr_number = "9999"
        pr_url = f"https://github.com/mock/repo/pull/{pr_number}"
        print(
            f"{COLOR_YELLOW}[DRY RUN] gh pr create --draft --base {args.base} "
            f"--title '{ticket_id}: {commit_subject}' --body:{COLOR_RESET}"
        )
        print(pr_body)
    else:
        try:
            pr_url = run_cmd(
                [
                    "gh",
                    "pr",
                    "create",
                    "--draft",
                    "--base",
                    args.base,
                    "--title",
                    f"{ticket_id}: {commit_subject}",
                    "--body",
                    pr_body,
                ],
                capture=True,
            )
            pr_number = pr_url.split("/")[-1]
        except SystemExit:
            print(
                f"{COLOR_YELLOW}Failed to create PR. Checking if one already exists...{COLOR_RESET}"
            )
            existing_url = run_cmd(
                ["gh", "pr", "view", "--json", "url", "--jq", ".url"], capture=True
            )
            if existing_url:
                pr_url = existing_url.strip()
                pr_number = pr_url.split("/")[-1]
                print(f"{COLOR_GREEN}Found existing PR: #{pr_number}{COLOR_RESET}")
            else:
                sys.exit(1)

    amended_msg = f"{ticket_id}: {commit_subject}\n\n{body_placeholder}\n\nPR #{pr_number}"

    print(f"{COLOR_CYAN}Applying PR number and validating commit...{COLOR_RESET}")
    if args.dry_run:
        print(f"{COLOR_YELLOW}[DRY RUN] git commit --amend --allow-empty -m '...'{COLOR_RESET}")
        print(f"{COLOR_YELLOW}[DRY RUN] Skipping interactive validation loop{COLOR_RESET}")
        print(f"{COLOR_YELLOW}[DRY RUN] git push --force-with-lease{COLOR_RESET}")
    else:
        # git-recommit reopens the editor and retries if a commit-msg hook rejects the message
        amend = ["git", "recommit", "--amend", "--allow-empty", "-m", amended_msg]
        if subprocess.run(amend).returncode != 0:
            print(
                f"{COLOR_RED}Aborted. Your branch and PR exist, "
                f"but the commit was not amended.{COLOR_RESET}"
            )
            sys.exit(1)

        run_cmd(["git", "push", "--force-with-lease"], capture=True)

    if args.dry_run:
        print(f"\n{COLOR_GREEN}[DRY RUN] Simulation complete!{COLOR_RESET}")
    else:
        print(f"\n{COLOR_GREEN}Success: Workflow complete!{COLOR_RESET}")
    print(f"  {COLOR_CYAN}Branch:{COLOR_RESET} {branch_name}")
    print(f"  {COLOR_CYAN}PR:{COLOR_RESET}     {pr_url}")


if __name__ == "__main__":
    main()
