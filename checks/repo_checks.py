#!/usr/bin/env python3
"""The checks every one of my repos runs, on my machine and in CI.

Run it from the top of any of my repos:

    python3 path/to/repo_checks.py

In CI the shared workflow runs the same file, so the two can't drift apart.
It only uses the Python standard library.

Each repo can switch checks on or off in .github/repo-checks.json:

    {
      "allow_en_dash": false,              # or "dates" to allow them only in date ranges
      "readme_must_link_dirs": "^\\d{2}-",  # top-level folders the README must link
      "skills": false                      # true in a repo of Claude skills
    }
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

NOREPLY = "275556488+Lily-Tewolde@users.noreply.github.com"
# GitHub's own address for browser edits and its merge button. Never personal.
GITHUB_COMMITTER = "noreply@github.com"
BOTS = {"41898282+github-actions[bot]@users.noreply.github.com"}

PROSE_EXTENSIONS = {".md", ".txt", ".csv"}
KEY_PATTERNS = [
    ("an Anthropic API key", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("a GitHub token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"),
    ("a GitHub token", r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    ("an AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("a private key", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
]
EM_DASH, EN_DASH = "\u2014", "\u2013"
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE_START = r"(?:\[Start\]|\b\d{4})"
_DATE_END = r"(?:\[End\]|Present\b|\d{4}\b|%s \d{4}\b)" % _MONTH
DATE_RANGE_EN_DASH = re.compile(_DATE_START + " " + EN_DASH + " " + _DATE_END)
MAX_DESCRIPTION = 200


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def tracked_files():
    return [Path(p) for p in git("ls-files", "-z").split("\0") if p]


def read_text(path):
    try:
        if path.stat().st_size > 2_000_000:
            return None
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def load_config():
    path = Path(".github/repo-checks.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# ---------------------------------------------------------------- dashes

def check_dashes(files, config):
    problems = []
    allow_en = config.get("allow_en_dash", False)
    dates_only = allow_en == "dates"
    for path in files:
        if path.suffix.lower() not in PROSE_EXTENSIONS:
            continue
        text = read_text(path)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if EM_DASH in line:
                problems.append(f"{path}:{number} has an em dash")
            if EN_DASH in line and allow_en is not True:
                leftover = DATE_RANGE_EN_DASH.sub("", line) if dates_only else line
                if EN_DASH in leftover:
                    where = " outside a date range" if dates_only else ""
                    problems.append(f"{path}:{number} has an en dash{where}")
    return problems


# ---------------------------------------------------------------- private files and keys

def check_private_files(files, config):
    return [f"{path} is private and shouldn't be committed" for path in files
            if "(private)" in path.name.lower() or path.name == "CLAUDE.md"]


def check_keys(files, config):
    problems = []
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for label, pattern in KEY_PATTERNS:
                if re.search(pattern, line):
                    problems.append(f"{path}:{number} looks like {label}")
    return problems


# ---------------------------------------------------------------- links

def github_slug(heading):
    """Turn a heading into the anchor GitHub gives it."""
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_~]", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def strip_code(text):
    text = re.sub(r"^(```|~~~).*?^\1", "", text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", text)


def anchors_in(path, cache):
    if path not in cache:
        text = read_text(path) or ""
        body = re.sub(r"^(```|~~~).*?^\1", "", text, flags=re.S | re.M)
        seen, anchors = {}, set()
        for heading in re.findall(r"^#{1,6}\s+(.*?)\s*#*\s*$", body, re.M):
            slug = github_slug(heading)
            count = seen.get(slug, 0)
            anchors.add(slug if count == 0 else f"{slug}-{count}")
            seen[slug] = count + 1
        anchors |= set(re.findall(r'<a\s+(?:name|id)="([^"]+)"', body))
        anchors |= set(re.findall(r'\sid="([^"]+)"', body))
        cache[path] = anchors
    return cache[path]


def check_links(files, config):
    problems, cache = [], {}
    root = Path.cwd().resolve()
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        text = read_text(path)
        if text is None:
            continue
        for target in re.findall(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)", strip_code(text)):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            link, _, fragment = target.partition("#")
            if link:
                resolved = (path.parent / urllib.parse.unquote(link)).resolve()
                if not resolved.exists():
                    problems.append(f"{path} links to {target}, which doesn't exist")
                    continue
                if root not in resolved.parents and resolved != root:
                    continue
            else:
                resolved = path.resolve()
            if fragment and resolved.is_file() and resolved.suffix.lower() == ".md":
                if urllib.parse.unquote(fragment).lower() not in {a.lower() for a in anchors_in(resolved, cache)}:
                    problems.append(f"{path} links to {target}, but there's no heading or anchor called #{fragment}")
    return problems


# ---------------------------------------------------------------- README lists every folder

def check_readme_lists_dirs(files, config):
    pattern = config.get("readme_must_link_dirs")
    if not pattern:
        return []
    readme = read_text(Path("README.md")) or ""
    folders = sorted({p.parts[0] for p in files if len(p.parts) > 1 and re.match(pattern, p.parts[0])})
    problems = []
    for folder in folders:
        linked = re.search(r"\]\((?:\./)?%s(?:/[^)]*)?\)" % re.escape(folder), readme) or \
            re.search(r"/tree/[^/)]+/%s(?:/|\))" % re.escape(folder), readme)
        if not linked:
            problems.append(f"README.md doesn't link to {folder}/")
    return problems


# ---------------------------------------------------------------- Claude skills

def frontmatter(text):
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith(" "):
            fields[key.strip()] = value.strip()
    return fields


def check_skills(files, config):
    if not config.get("skills"):
        return []
    problems = []
    names = {p.as_posix() for p in files}
    for folder in sorted({p.parts[0] for p in files if len(p.parts) == 2 and p.name == "SKILL.md"}):
        fields = frontmatter(read_text(Path(folder) / "SKILL.md") or "")
        if fields is None:
            problems.append(f"{folder}/SKILL.md has no frontmatter")
            continue
        for key in ("name", "description", "license"):
            if not fields.get(key):
                problems.append(f"{folder}/SKILL.md has no {key}")
        if fields.get("name") and fields["name"] != folder:
            problems.append(f"{folder}/SKILL.md is named {fields['name']}, not {folder}")
        description = fields.get("description", "")
        if len(description) >= MAX_DESCRIPTION:
            problems.append(f"{folder}/SKILL.md description is {len(description)} characters, needs to be under {MAX_DESCRIPTION}")
        if ":" in description:
            problems.append(f"{folder}/SKILL.md description has a colon, so it may not load")
        if f"{folder}/README.md" not in names:
            problems.append(f"{folder}/ has no README.md")
        if not any(n.startswith(f"{folder}/LICENSE") for n in names):
            problems.append(f"{folder}/ has no LICENSE")
    return problems


# ---------------------------------------------------------------- commit emails

def commit_range(explicit):
    if explicit:
        return explicit
    event = os.environ.get("GITHUB_EVENT_NAME")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event and event_path and Path(event_path).exists():
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        if event == "pull_request":
            return f"{payload['pull_request']['base']['sha']}..{payload['pull_request']['head']['sha']}"
        if event == "push":
            before, after = payload.get("before", ""), payload.get("after", "")
            if before and set(before) != {"0"}:
                return f"{before}..{after}"
        return None
    for candidate in ("@{upstream}", "origin/HEAD"):
        try:
            git("rev-parse", "--verify", "--quiet", candidate)
            return f"{candidate}..HEAD"
        except subprocess.CalledProcessError:
            continue
    return None


def check_commit_emails(files, config, revision_range=None):
    if not revision_range:
        return []
    problems = []
    try:
        log = git("log", "--format=%h%x09%ae%x09%ce", revision_range)
    except subprocess.CalledProcessError:
        return [f"couldn't read the commits in {revision_range}"]
    for line in log.splitlines():
        sha, author, committer = line.split("\t")
        if author != NOREPLY and author not in BOTS:
            problems.append(f"commit {sha} has author email {author}")
        if committer not in {NOREPLY, GITHUB_COMMITTER} and committer not in BOTS:
            problems.append(f"commit {sha} has committer email {committer}")
    return problems


# ---------------------------------------------------------------- run them all

CHECKS = [
    ("No em dashes, and en dashes only where allowed", check_dashes),
    ("No private files", check_private_files),
    ("No keys or tokens", check_keys),
    ("Every link and anchor works", check_links),
    ("The README links every folder it should", check_readme_lists_dirs),
    ("Every skill is complete", check_skills),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run my repo checks.")
    parser.add_argument("--commits", help="commit range for the email check, like origin/main..HEAD")
    args = parser.parse_args(argv)

    files = tracked_files()
    config = load_config()
    failed = False
    results = [(label, check(files, config)) for label, check in CHECKS]
    revision_range = commit_range(args.commits)
    results.append((f"Every new commit uses my noreply email ({revision_range or 'no commits to check'})",
                    check_commit_emails(files, config, revision_range)))
    for label, problems in results:
        print(f"{'FAIL' if problems else 'ok  '}  {label}")
        for problem in problems:
            print(f"        {problem}")
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
