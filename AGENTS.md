# Requiem project instructions

These instructions apply to development tasks in this repository. Honor the
user's current task scope and any more specific project instructions.

## Publish completed tasks to GitHub

The user authorizes a meaningful commit and ordinary push after each completed
feature, bug fix, UI improvement, code change or documentation task, once the
relevant verification passes. Do not ask for publishing permission again merely
because a task is ready. Follow [the publishing workflow](docs/GITHUB_SYNC.md).

- Target repository: `ashishkapadi/AquaSetu`.
- Existing remote: `origin`; never silently replace its URL or Git configuration.
- Use the task's existing attached branch. The setup branch is `main`, tracking
  `origin/main`. Never force-push or rewrite/delete history.
- Publish once per completed task, not after file saves or individual edits.
- Do not publish incomplete tasks, failed tests/checks, unresolved merge conflicts,
  unexplained fatal runtime diagnostics, or changes the user says not to publish.
- Inspection-only tasks do not require a commit. No changes means no empty commit.
- At task start, record HEAD, branch, working-tree changes and staged entries.
  Preserve all pre-existing changes, including the user's index. Never use broad
  staging, automatic stashing, resets, cleanup, or automatic conflict resolution.
- Stage only an explicit reviewed list of task-owned files. If a file contains
  earlier unrelated edits, do not commit it wholesale. Isolate the task safely or
  report the publishing blocker without discarding the user's work.
- Run relevant tests and checks, inspect the complete candidate files and actual
  commit delta for secrets/sensitive data, and verify the exact commit contents.
  Never include credentials, real `.env` files, caches, virtual environments,
  generated temporary files or unnecessary artifacts. Ignore rules are not a
  secret scanner and do not protect already-tracked files.
- Stop on authentication failure or push rejection and explain the cause. Never
  force, bypass protections, change authentication/configuration, or merge/rebase
  automatically to make publishing succeed. Ask before authentication or Git
  configuration changes when necessary.
- Report checks, commit ID/message, branch and push result. Distinguish committed
  locally from published remotely. Explain any block instead of claiming success.

This is an agent-driven task-completion policy. It relies on the agent loading
and following these instructions; no file watcher, Git hook, background service,
scheduled task or CI publisher is installed. IDE/sandbox permission controls still
apply. Open this repository as the Antigravity workspace so its root instructions
are discoverable.

## Application preservation

Keep the Streamlit dashboard in `Dashboard/jalbach/` and the React landing page in
`frontend/` separate. Preserve the separate forecasting pipelines, data contracts,
allocation logic, datasets, source distinctions and existing functionality unless
the user explicitly authorizes a relevant change. Do not enter unrelated nested
projects or configure deployments as part of Git publishing.
