"""Behavioral tests for scripts/release.py SemVer and idempotent release logic."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release  # noqa: E402


class ReleasePureLogicTests(unittest.TestCase):
    def test_parse_and_bump_semver_enforce_strict_triplets(self):
        self.assertEqual(release.parse_semver("3.6.2"), (3, 6, 2))
        self.assertEqual(release.bump_semver("3.6.2", "patch"), "3.6.3")
        self.assertEqual(release.bump_semver("3.6.2", "minor"), "3.7.0")
        self.assertEqual(release.bump_semver("3.6.2", "major"), "4.0.0")
        for invalid in ("v3.6.2", "3.6", "01.2.3", "3.6.2-rc1", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    release.parse_semver(invalid)

    def test_classify_commits_follows_conventional_semver_hierarchy(self):
        bump, bullets = release.classify_commits(
            [
                ("docs: update CLI flags", ""),
                ("ci: pin action SHAs", ""),
            ]
        )
        self.assertIsNone(bump)
        self.assertEqual(bullets, ["Update CLI flags.", "Pin action SHAs."])

        bump, bullets = release.classify_commits(
            [
                ("refactor: remove dead storage", ""),
                ("fix(control): close symlink race", ""),
                ("chore(release): prepare v3.6.2", ""),
            ]
        )
        self.assertEqual(bump, "patch")
        self.assertEqual(bullets, ["Remove dead storage.", "Close symlink race."])

        bump, bullets = release.classify_commits(
            [
                ("fix(panel): polish snooze row", ""),
                ("feat(control): add --skip-brightness fast path", ""),
            ]
        )
        self.assertEqual(bump, "minor")
        self.assertEqual(
            bullets,
            ["Polish snooze row.", "Add --skip-brightness fast path."],
        )

        bump, _ = release.classify_commits([("feat(api)!: drop legacy format", "")])
        self.assertEqual(bump, "major")

        bump, _ = release.classify_commits([("fix: change schema", "BREAKING CHANGE: schema 2")])
        self.assertEqual(bump, "major")

    def test_prepend_changelog_is_idempotent_and_preserves_history(self):
        initial = (
            "# Changelog\n\n"
            "Release versions correspond to `manifest.json`.\n\n"
            "## v3.6.2 (2026-11-04)\n\n"
            "- Existing historical note.\n"
        )
        updated = release.prepend_changelog(
            initial,
            "3.7.0",
            "2026-11-17",
            ["Add fast path.", "Adopt ShellIpc."],
        )
        self.assertIn("## v3.7.0 (2026-11-17)\n\n- Add fast path.\n- Adopt ShellIpc.\n\n## v3.6.2", updated)
        self.assertEqual(
            release.prepend_changelog(updated, "3.7.0", "2026-11-17", ["Different."]),
            updated,
        )


class ReleaseGitStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self._git("init", "-b", "main")
        self._write_repo_files("3.6.2")
        self._git("add", ".")
        self._commit("chore(release): prepare v3.6.2")
        self._tag("v3.6.2", "Veilleuse 3.6.2")

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(self.repo),
            text=True,
            capture_output=True,
            check=True,
        )

    def _commit(self, message: str) -> None:
        self._git(
            "-c", "user.name=Pumpkin",
            "-c", "user.email=169100552+ZnOw01@users.noreply.github.com",
            "commit", "--allow-empty", "-m", message,
        )

    def _tag(self, name: str, message: str) -> None:
        self._git(
            "-c", "user.name=Pumpkin",
            "-c", "user.email=169100552+ZnOw01@users.noreply.github.com",
            "tag", "-a", name, "-m", message,
        )

    def _write_repo_files(self, version: str) -> None:
        (self.repo / "manifest.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "id": "io.github.znow01.veilleuse",
                    "name": "Veilleuse",
                    "version": version,
                    "entryPoints": {"barWidget": "BarWidget.qml"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## v3.6.2 (2026-11-04)\n\n- Previous release.\n",
            encoding="utf-8",
        )

    def test_already_tagged_head_does_not_loop_or_commit(self):
        plan = release.plan_release(self.repo)
        self.assertEqual(plan["action"], "ensure_tag_and_release")
        self.assertFalse(plan["needs_commit"])
        self.assertFalse(plan["needs_tag"])

    def test_docs_only_commits_skip_release_unless_override_requested(self):
        self._commit("docs: clarify shortcut section")
        skipped = release.plan_release(self.repo)
        self.assertEqual(skipped["action"], "skip_no_releasable_commits")

        forced = release.plan_release(self.repo, bump_override="patch", release_date="2026-11-17")
        self.assertEqual(forced["action"], "release")
        self.assertEqual(forced["target_version"], "3.6.3")

    def test_apply_release_bumps_manifest_prepends_changelog_and_tags_idempotently(self):
        self._commit("fix(control): reap stale state temp files")
        self._commit("feat(control): add --skip-brightness fast path")

        applied = release.apply_release(self.repo, release_date="2026-11-17", push=False)
        self.assertEqual(applied["target_version"], "3.7.0")
        self.assertTrue(applied["committed"])

        manifest = json.loads((self.repo / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "3.7.0")
        changelog = (self.repo / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## v3.7.0 (2026-11-17)", changelog)
        self.assertIn("## v3.6.2 (2026-11-04)", changelog)

        tags = self._git("tag", "--points-at", "HEAD").stdout.split()
        self.assertIn("v3.7.0", tags)

        # Second invocation on the release commit is a safe idempotent no-op.
        second = release.apply_release(self.repo, release_date="2026-11-17", push=False)
        self.assertEqual(second["action"], "ensure_tag_and_release")
        self.assertFalse(second["committed"])

    def test_apply_release_falls_back_to_gh_release_target_when_tag_push_rejected(self):
        from unittest import mock

        self._commit("feat(control): add --skip-brightness fast path")
        real_run = release._run
        gh_calls = []

        def fake_run(cmd, *, cwd, check=True, input_text=None):
            if cmd[:3] == ["git", "push", "origin"]:
                if cmd[3].startswith("refs/tags/"):
                    return subprocess.CompletedProcess(cmd, 1, "", "remote rejected tag push")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[0] == "gh":
                gh_calls.append((list(cmd), input_text))
                if cmd[:3] == ["gh", "release", "view"]:
                    return subprocess.CompletedProcess(cmd, 1, "", "not found")
                return subprocess.CompletedProcess(cmd, 0, "https://example.invalid/v3.7.0\n", "")
            return real_run(cmd, cwd=cwd, check=check, input_text=input_text)

        with mock.patch.object(release, "_run", side_effect=fake_run):
            applied = release.apply_release(self.repo, release_date="2026-11-17", push=True)

        self.assertTrue(applied["published"])
        create_cmds = [cmd for cmd, _ in gh_calls if cmd[:3] == ["gh", "release", "create"]]
        self.assertEqual(len(create_cmds), 1)
        self.assertIn("--target", create_cmds[0])


if __name__ == "__main__":
    unittest.main()
