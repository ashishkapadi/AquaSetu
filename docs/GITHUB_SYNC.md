# Requiem task-completion GitHub publishing

## Configuration and scope

Repository: `D:\Ashish\projects\Requiem`.
Remote: `origin`, `https://github.com/ashishkapadi/AquaSetu.git`.
Setup branch: `main`, tracking `origin/main`.

The root `AGENTS.md` instructs compatible agents to finish, verify, review,
commit and push each successful development task. This is persistent agent
guidance, not a daemon or an enforced server-side gate. File saves do not publish.
An agent must load these instructions and actually run the workflow. IDE/sandbox
approvals and GitHub branch protections remain in force.

Antigravity's official [rules documentation](https://antigravity.google/docs/rules/)
supports root `AGENTS.md` as an always-active workspace rule. Open Requiem as the
workspace and, in a new session, verify that the root instructions are loaded.
This setup does not claim an Antigravity UI/session activation test. The official
[legacy workflow documentation](https://antigravity.google/docs/ide/workflows/)
announces retirement of that format on October 19, 2026; this setup uses project
instructions and the checklist below instead of a retired slash-workflow file.

No Git remote, credential helper, commit identity or global IDE permissions were
changed. Existing history was not rewritten. No hooks or deployment integrations
were installed. Vercel and Render configuration is outside scope.

## Initial inspection, November 5, 2026

- Existing Git repository, branch `main`, upstream `origin/main`.
- Initial local and remote HEAD:
  `76bae4a763de29c06fbf42d73339b1b5da86dfee` (one initial commit).
- Both fetch/push URLs already point to the requested GitHub repository.
- Git Credential Manager is configured by the existing Git installation. Existing
  name/email settings are present. GitHub CLI is not installed/on PATH; it is not
  required for HTTPS Git publishing.
- A noninteractive remote query and `git push --dry-run --porcelain origin
  HEAD:refs/heads/main` succeeded using existing authentication. No commit or
  remote ref was created by that dry run. The initial sandbox attempt could not
  reach GitHub; the permitted network retry succeeded.
- Only sample hook files exist, and `core.hooksPath` is unset. No existing root
  agent rules, GitHub Actions or task-publishing automation were found.
- Numerous earlier modifications, additions and deletions exist across the
  dashboard, frontend and backend, plus unrelated untracked files. Eight paths
  already have staged changes. They are not part of this configuration task.
- Existing ignore rules cover `.env`, `.env.*`, private key extensions, dependency
  directories, virtual environments, logs and artifacts. This setup extends
  credential/Streamlit-secret protection across nested apps and ignores local
  root-level recordings and macOS metadata. Existing exceptions remain intact.
  The allowed `.env.example` exception is only for explicitly reviewed sanitized
  templates; never publish real environment values there.

## Required workflow for every development task

### 1. Establish ownership before editing

Record the task scope, current HEAD/branch, `git status --short`, existing staged
paths and their staged blob IDs. Review current changes before deciding what the
task owns. Do not assume every dirty file belongs to the task.

Verify `git remote -v`, upstream and absence of in-progress merge/rebase/cherry-pick
or unresolved entries (`git ls-files -u`). A detached HEAD, unexpected remote,
unrelated unpublished commits, or unresolved operation blocks automatic publishing.
Do not silently change branches or Git configuration. Fetch the intended remote
branch when connectivity permits; if it has advanced, stop and report divergence
rather than automatically rebasing/merging. A normal push must remain fast-forward.

### 2. Complete and verify the task

Implement the requested scope, then run the relevant tests/checks and record exact
commands and exit codes. Choose checks appropriate to the change: application
tests for code, actual browser review for UI, and link/configuration checks for
documentation/ignore-rule changes. Recheck after material fixes. Do not publish
when required tests fail, work is incomplete, or the user requests no publishing.
Investigate/report fatal diagnostics even if a runner returns zero; do not label
them a clean pass or publish unresolved potentially material failures.

If only documentation/configuration changed, do not run unrelated slow app suites
solely to manufacture a test result. Explain the relevant checks actually run.

### 3. Review content and secrets before staging

Build an explicit repository-relative candidate-file list. Review full contents,
diffs, new files, deletions and binary-file purpose. Check for real API keys,
passwords, access tokens, private keys, connection strings with credentials,
personal/sensitive datasets, `.env` files and credential stores. Use an available
approved scanner as an additional check when useful; do not expose secret values
in tool output. Report suspicious file/line locations only. Never blindly add an
allowlist to suppress a finding.

Check `git check-ignore -v --no-index -- <candidate>` where appropriate and inspect
already-tracked sensitive names separately (`git ls-files`). `.gitignore` only
prevents ordinary addition of untracked paths. It neither scans contents nor
removes historical/tracked secrets. A suspected existing secret blocks publication;
report it and discuss revocation/remediation without rewriting history.

Exclude dependencies, virtual environments, caches, logs, generated artifacts,
recordings, build outputs and unrelated projects. Never use `git add .`, `git add
-A`, `git commit -a`, `git clean`, destructive reset, automatic stash, or force-add
to get around ignore rules.

### 4. Stage and commit only reviewed task content

Stage explicit literal file paths. Use `git --literal-pathspecs add -- <paths>`
and review `git diff --cached -- <paths>` plus `git diff --check -- <paths>`.
Do not include pre-existing unrelated staged paths in a plain `git commit`.

When each candidate file is wholly owned by this task, an explicit
`git --literal-pathspecs commit --only -m "type: meaningful result" -- <paths>`
commits those files while preserving other staged paths. **`--only` takes the
listed files' working-tree content**, not merely staged hunks: do not use it to
publish selected hunks from a file with earlier unrelated changes. If safe
isolation cannot be established, stop publication and explain the conflict.

Use meaningful messages such as `feat: improve demand forecast workspace`,
`fix: resolve dashboard map rendering issue`, `ui: improve mobile dashboard
layout`, or `docs: update deployment instructions`. Do not create empty commits.
Never disable hooks/checks or amend/rewrite older commits to publish a task.

After committing, verify `git show --stat --oneline HEAD` and the actual changed
path list against the candidate list. Review the final commit delta for secrets.
Confirm unrelated working-tree changes and staged blob IDs are unchanged. If the
commit includes unintended content, do not push or automatically rewrite history;
report the problem for a safe correction.

### 5. Push and verify

Verify origin still belongs to `ashishkapadi/AquaSetu`, the attached branch is the
same task branch, and all outgoing commits are intended. Never blindly push earlier
local commits simply because they precede the new one. Use a normal explicit push
to the same branch, for example on `main`:

```powershell
git push origin HEAD:refs/heads/main
git ls-remote --heads origin main
git rev-parse HEAD
```

Compare remote branch SHA with local HEAD. Only then report remotely published.
A push rejection stops the workflow: preserve the local commit and explain remote
advancement, branch protection, permission/network error, or other stated cause.
Never retry with force or bypass protections. If the push outcome is ambiguous,
query the remote before doing anything else.

If authentication fails, stop without logging a token or changing credential
settings. Explain that the user can authenticate interactively with their existing
Git Credential Manager, or use `gh auth login` if they choose to install/use GitHub
CLI. Do not install tools or change authentication without approval. Never embed
a token in a remote URL, a script, a document, or a command argument.

### 6. Report completion

Report intended changed files, relevant checks/results, commit ID/message, branch,
push success/failure and any preserved unrelated changes or blockers. If inspection
found no changes, report that no commit was necessary. Do not claim agent guidance
is a guaranteed background synchronization service.

## Safe verification without extra commits

Setup checks passed for 23 representative sensitive/generated paths being ignored
and six intended source/template paths remaining eligible. Local documentation
links, branch/remote, absence of unresolved index entries, and the original index
fingerprint were verified. Candidate-file private-key/token/credential-URL pattern
checks found no matches; manual review of all three setup files was also performed.
No tracked `.env`, private-key-extension or Streamlit secret filenames were found.
These checks do not constitute a complete historical secret audit. No application
source changed, so application tests were not rerun for this configuration task.

```powershell
git remote -v
git branch -vv
git status --short --branch
git ls-files -u
git check-ignore -v --no-index -- .env backend/.env frontend/.env.local Dashboard/jalbach/.streamlit/secrets.toml .aws/credentials .venv/pyvenv.cfg node_modules/example/index.js artifacts/check.log
git ls-remote --heads origin main
git push --dry-run --porcelain origin HEAD:refs/heads/main
```

Dry runs do not prove all branch-protection checks for a new commit will pass.
Final setup results and the setup-only commit/push outcome are reported in the
completion message. Existing development changes are not published by this setup.
