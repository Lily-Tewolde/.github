# How I run my repos

The practices my public repos follow, and the ones I'm adding as I learn. I measure against [OpenSSF Scorecard](https://github.com/ossf/scorecard), the free checklist open source projects use to grade a repo on things like branch protection, workflow permissions and pinned dependencies. That way I'm working to a bar senior engineers already use, not one I made up.

## In place now

1. **The same checks run on my machine and in CI.** One script, [`checks/repo_checks.py`](checks/repo_checks.py), runs before I push and on every pull request. Catching a problem before the push is cheaper than catching it after.
2. **The checks are tested too.** Every check has tests that break something on purpose and make sure it gets caught. A check that can't fail isn't a check.
3. **Workflows are locked down.** Every workflow is read-only unless it needs more. Every outside action is pinned to an exact commit, with its version in a comment, so the code a workflow runs can't change underneath me. My own shared workflow tracks `main` on purpose, so a fix here reaches every repo the same day.
4. **I check before every push.** Each issue's numbered list gets checked item by item, the pages get rendered the way GitHub shows them, and any change to a Claude file or skill gets a dry run on a made-up case. Fixes stay small and land in the PR they belong to.
5. **Every PR says what it closes.** `Fixes #N` for every issue, and a title that names the outcome, not the mechanism.

## Next, once the checks are green

| Practice | Why |
|---|---|
| **Protect `main`.** Changes only through pull requests, with the checks required and no force-pushing | A red check should stop a merge, not just warn about it. Free on public repos |
| **Push protection for secrets** | GitHub refuses a push that contains a key. CI can only tell me after it's public |
| **Default PR and issue templates** in this repo | The PR template is the four parts from my PR lesson: what, why, how I checked it and what's not in this PR. The issue template asks for numbered acceptance criteria, which is what makes checking a fix possible |

## Later, as I learn

| Practice | Why | What I'll pair it with |
|---|---|---|
| **Run Scorecard monthly** and fix one finding at a time | An outside grade shows me what I don't know to look for | A short note on what my repo scored and why |
| **Keep the dry-run inputs as fixtures,** and rerun them whenever a skill or Claude file changes | Instructions drift the same way prompts do. This is evals for instructions | My golden set lessons |
| **Automatic dependency updates** with Dependabot, only in repos that have dependencies | Outdated libraries are how most known security holes get in | My evals in CI lesson, which has a `requirements.txt` |
| **Signed commits** | My commits show as Verified, so anyone can tell they're really mine | Cleaning up my old unverified commits |
| **A local pre-push hook** that runs the same script | Stops a commit with the wrong email before it's public, not after | My email rule |

## Skipped for now

- **Required reviewers and CODEOWNERS.** I'm the only person working on these repos.
- **Release tags and changelogs.** Worth it once people install my skills by version.
- **Some repos stay as they are.** Private repos, and anything I've been asked not to change.
