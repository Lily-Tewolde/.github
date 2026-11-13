"""Tests for repo_checks.py. Each one builds a tiny git repo, breaks one thing
on purpose and makes sure the right check catches it.

Run them with:  python3 -m unittest discover -s checks
"""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import repo_checks as rc

ME = rc.NOREPLY


def sh(*args, env=None):
    subprocess.run(args, check=True, capture_output=True, env=env)


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        sh("git", "init", "-q", "-b", "main")
        sh("git", "config", "user.name", "Test")
        sh("git", "config", "user.email", ME)
        sh("git", "config", "commit.gpgsign", "false")

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def write(self, name, text):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        sh("git", "add", name)

    def config(self, **values):
        self.write(".github/repo-checks.json", json.dumps(values))

    def commit(self, message="Change", author=ME, committer=ME):
        env = dict(os.environ, GIT_AUTHOR_EMAIL=author, GIT_COMMITTER_EMAIL=committer,
                   GIT_AUTHOR_NAME="Test", GIT_COMMITTER_NAME="Test")
        sh("git", "commit", "-q", "--allow-empty", "-m", message, env=env)

    def run_checks(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = rc.main(list(args))
        return code, out.getvalue()


class CleanRepo(RepoTest):
    def test_a_clean_repo_passes_every_check(self):
        self.write("README.md", "# Hi\n\nSee [the guide](01-guide/) and [below](#more).\n\n## More\n")
        self.write("01-guide/README.md", "# Guide\n")
        self.config(readme_must_link_dirs=r"^\d{2}-")
        self.commit()
        code, out = self.run_checks("--commits", "HEAD~0..HEAD")
        self.assertEqual(code, 0, out)


class Dashes(RepoTest):
    def test_em_dash_fails(self):
        self.write("a.md", "One \u2014 two\n")
        self.assertIn("a.md:1 has an em dash", rc.check_dashes(rc.tracked_files(), {}))

    def test_en_dash_fails_unless_allowed(self):
        self.write("a.md", "June 2022 \u2013 Present\n")
        self.assertTrue(rc.check_dashes(rc.tracked_files(), {}))
        self.assertFalse(rc.check_dashes(rc.tracked_files(), {"allow_en_dash": True}))

    def test_dates_setting_allows_date_ranges_only(self):
        self.write("a.md", "June 2022 \u2013 Present\n([Start] \u2013 [End])\nSept 2022 \u2013 May 2024\nSummers 2023 \u2013 2024\n")
        self.assertFalse(rc.check_dashes(rc.tracked_files(), {"allow_en_dash": "dates"}))
        self.write("b.md", "Pages 4 \u2013 7, and this \u2013 one, are not date ranges\n")
        problems = rc.check_dashes(rc.tracked_files(), {"allow_en_dash": "dates"})
        self.assertEqual(problems, ["b.md:1 has an en dash outside a date range"])

    def test_code_files_are_left_alone(self):
        self.write("a.py", "x = 1  # \u2014\n")
        self.assertFalse(rc.check_dashes(rc.tracked_files(), {}))


class PrivateAndKeys(RepoTest):
    def test_private_file_fails(self):
        self.write("00 PLAN (private).md", "secret\n")
        self.assertTrue(rc.check_private_files(rc.tracked_files(), {}))

    def test_claude_md_fails(self):
        self.write("CLAUDE.md", "rules\n")
        self.assertTrue(rc.check_private_files(rc.tracked_files(), {}))

    def test_key_fails(self):
        self.write("a.txt", "key = sk-ant-" + "a" * 30 + "\n")
        self.assertIn("a.txt:1 looks like an Anthropic API key", rc.check_keys(rc.tracked_files(), {}))

    def test_talking_about_keys_passes(self):
        self.write("a.md", "Set ANTHROPIC_API_KEY in your own terminal.\n")
        self.assertFalse(rc.check_keys(rc.tracked_files(), {}))


class Links(RepoTest):
    def test_missing_file_fails(self):
        self.write("a.md", "[x](nope.md)\n")
        self.assertTrue(rc.check_links(rc.tracked_files(), {}))

    def test_missing_heading_fails(self):
        self.write("a.md", "[x](b.md#nowhere)\n")
        self.write("b.md", "# Somewhere\n")
        self.assertTrue(rc.check_links(rc.tracked_files(), {}))

    def test_heading_with_punctuation_and_emoji_passes(self):
        self.write("a.md", "[x](b.md#step-1-gather-everything-)\n[y](b.md#keeping-someone-elses-resume-private)\n")
        self.write("b.md", "## Step 1: Gather everything \U0001F916\n\n## Keeping someone else's resume private\n")
        self.assertFalse(rc.check_links(rc.tracked_files(), {}))

    def test_repeated_heading_gets_a_number(self):
        self.write("a.md", "[x](#notes-1)\n\n## Notes\n\n## Notes\n")
        self.assertFalse(rc.check_links(rc.tracked_files(), {}))

    def test_html_anchor_passes(self):
        self.write("a.md", "[x](b.md#terminal-route)\n")
        self.write("b.md", '<a name="terminal-route"></a>\n')
        self.assertFalse(rc.check_links(rc.tracked_files(), {}))

    def test_web_links_and_code_are_skipped(self):
        self.write("a.md", "[x](https://example.com/nope)\n`[y](nope.md)`\n```\n[z](nope.md)\n```\n")
        self.assertFalse(rc.check_links(rc.tracked_files(), {}))

    def test_encoded_file_name_passes(self):
        self.write("My Rules.md", "# Rules\n")
        self.write("a.md", "[x](My%20Rules.md)\n")
        self.assertFalse(rc.check_links(rc.tracked_files(), {}))


class ReadmeAndSkills(RepoTest):
    def test_unlisted_folder_fails(self):
        self.write("README.md", "# Hi\n")
        self.write("02-thing/README.md", "# Thing\n")
        problems = rc.check_readme_lists_dirs(rc.tracked_files(), {"readme_must_link_dirs": r"^\d{2}-"})
        self.assertEqual(problems, ["README.md doesn't link to 02-thing/"])

    def skill(self, name="demo", description="Does a thing. Use for things.", files=("README.md", "LICENSE")):
        self.write(f"{name}/SKILL.md", f"---\nname: {name}\ndescription: {description}\nlicense: MIT\n---\n\n# Demo\n")
        for f in files:
            self.write(f"{name}/{f}", "x\n")

    def test_complete_skill_passes(self):
        self.skill()
        self.assertFalse(rc.check_skills(rc.tracked_files(), {"skills": True}))

    def test_long_description_fails(self):
        self.skill(description="x" * 200)
        self.assertTrue(rc.check_skills(rc.tracked_files(), {"skills": True}))

    def test_colon_in_description_fails(self):
        self.skill(description="Resume builder: tailors it")
        self.assertTrue(rc.check_skills(rc.tracked_files(), {"skills": True}))

    def test_missing_license_fails(self):
        self.skill(files=("README.md",))
        self.assertIn("demo/ has no LICENSE", rc.check_skills(rc.tracked_files(), {"skills": True}))

    def test_name_must_match_folder(self):
        self.write("demo/SKILL.md", "---\nname: other\ndescription: Fine.\nlicense: MIT\n---\n")
        self.write("demo/README.md", "x\n")
        self.write("demo/LICENSE", "x\n")
        self.assertIn("demo/SKILL.md is named other, not demo", rc.check_skills(rc.tracked_files(), {"skills": True}))


class CommitEmails(RepoTest):
    def setUp(self):
        super().setUp()
        self.commit("Base")

    def test_personal_email_fails(self):
        self.commit("Oops", author="someone@example.com")
        problems = rc.check_commit_emails([], {}, "HEAD~1..HEAD")
        self.assertTrue(any("author email someone@example.com" in p for p in problems))

    def test_github_as_committer_passes(self):
        self.commit("Merged on GitHub", committer=rc.GITHUB_COMMITTER)
        self.assertFalse(rc.check_commit_emails([], {}, "HEAD~1..HEAD"))

    def test_github_as_author_fails(self):
        self.commit("Odd", author=rc.GITHUB_COMMITTER)
        self.assertTrue(rc.check_commit_emails([], {}, "HEAD~1..HEAD"))

    def test_actions_bot_passes(self):
        bot = next(iter(rc.BOTS))
        self.commit("Update guide count", author=bot, committer=bot)
        self.assertFalse(rc.check_commit_emails([], {}, "HEAD~1..HEAD"))

    def test_unreadable_range_is_reported_not_crashed(self):
        self.assertEqual(rc.check_commit_emails([], {}, "nope..HEAD"), ["couldn't read the commits in nope..HEAD"])

    def test_failed_check_fails_the_run(self):
        self.write("a.md", "One \u2014 two\n")
        self.commit()
        code, out = self.run_checks("--commits", "HEAD~1..HEAD")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)


if __name__ == "__main__":
    unittest.main()
