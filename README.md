# .github

The checks and practices shared by my public repos. One script runs the same checks on my machine before I push and in CI on every pull request, so the two never drift apart. How I run my repos, and what I'm adding next, is in [PRACTICES.md](PRACTICES.md).

## What it checks

1. No em dashes anywhere, and no en dashes unless the repo allows them, or allows them only in date ranges
2. Every link and anchor inside the repo works
3. No private files or `CLAUDE.md` committed
4. No API keys, tokens or private keys
5. The README links every folder it should, like every lesson or guide
6. Every Claude skill has its frontmatter, a description under 200 characters with no colons, a README and a LICENSE
7. Every new commit uses my noreply email. GitHub's own address is allowed as committer, for browser edits and its merge button

## Run it on your machine

From the top of any of my repos:

```bash
python3 path/to/.github/checks/repo_checks.py
```

It only uses the Python standard library, so there's nothing to install. Add `--commits origin/main..HEAD` to check a different range of commits.

## Use it in a repo

Add `.github/workflows/checks.yml`:

```yaml
name: Checks

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  repo-checks:
    uses: Lily-Tewolde/.github/.github/workflows/repo-checks.yml@main
```

Then switch checks on or off in `.github/repo-checks.json`:

```json
{
  "allow_en_dash": "dates",
  "readme_must_link_dirs": "^\\d{2}-",
  "skills": false
}
```

| Setting | What it does | Default |
|---|---|---|
| `allow_en_dash` | `false` blocks every en dash, `"dates"` allows them only in date ranges like June 2022 to Present, `true` allows them all | `false` |
| `readme_must_link_dirs` | A pattern for the top-level folders the README has to link | off |
| `skills` | Checks every folder with a `SKILL.md` | `false` |

## The tests

Every check has tests that break something on purpose and make sure it gets caught:

```bash
python3 -m unittest discover -s checks
```

---

Made by [Lily Tewolde](https://github.com/Lily-Tewolde).
