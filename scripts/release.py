#!/usr/bin/env python3
"""Automated SemVer version bump, changelog update, tag, and GitHub release."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
GIT_AUTHOR_NAME = "Pumpkin"
GIT_AUTHOR_EMAIL = "169100552+ZnOw01@users.noreply.github.com"

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)\r\n]+)\))?(?P<bang>!)?:\s*(?P<summary>.+)$"
)
_BREAKING_BODY_RE = re.compile(r"(?m)^BREAKING[ -]CHANGE:\s*\S")
_RELEASE_COMMIT_RE = re.compile(r"^chore\(release\):\s*prepare\s+v(?P<version>\d+\.\d+\.\d+)\s*$")

_BUMP_RANK = {None: 0, "patch": 1, "minor": 2, "major": 3}
_PATCH_TYPES = frozenset({"fix", "perf", "refactor", "style", "revert"})
_NON_BUMP_TYPES = frozenset({"docs", "ci", "test", "chore", "build"})


class ReleaseError(RuntimeError):
    """Raised when a release invariant or git precondition fails."""


def parse_semver(version: str) -> tuple[int, int, int]:
    if not isinstance(version, str):
        raise ValueError(f"Invalid SemVer: {version!r}")
    match = _SEMVER_RE.fullmatch(version.strip())
    if match is None:
        raise ValueError(f"Invalid SemVer: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def format_semver(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def bump_semver(version: str, bump: str) -> str:
    major, minor, patch = parse_semver(version)
    if bump == "major":
        return format_semver((major + 1, 0, 0))
    if bump == "minor":
        return format_semver((major, minor + 1, 0))
    if bump == "patch":
        return format_semver((major, minor, patch + 1))
    raise ValueError(f"Unsupported bump kind: {bump!r}")


def _format_bullet(summary: str) -> str:
    cleaned = " ".join(summary.strip().split())
    if not cleaned:
        return ""
    if cleaned[0].isalpha() and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def classify_commits(commits: list[tuple[str, str]]) -> tuple[str | None, list[str]]:
    """Return ``(bump, bullets)`` for ``[(subject, body), ...]`` in chronological order."""
    highest: str | None = None
    primary_bullets: list[str] = []
    secondary_bullets: list[str] = []

    for raw_subject, raw_body in commits:
        subject = raw_subject.strip()
        body = raw_body or ""
        if not subject or _RELEASE_COMMIT_RE.match(subject):
            continue

        match = _CONVENTIONAL_RE.match(subject)
        is_breaking = bool(_BREAKING_BODY_RE.search(body))
        if match is not None:
            commit_type = match.group("type")
            if match.group("bang") == "!":
                is_breaking = True
            summary = match.group("summary")
            if is_breaking:
                commit_bump: str | None = "major"
            elif commit_type == "feat":
                commit_bump = "minor"
            elif commit_type in _PATCH_TYPES:
                commit_bump = "patch"
            elif commit_type in _NON_BUMP_TYPES:
                commit_bump = None
            else:
                commit_bump = "patch"
        else:
            commit_type = "other"
            summary = subject
            commit_bump = "major" if is_breaking else "patch"

        if _BUMP_RANK[commit_bump] > _BUMP_RANK[highest]:
            highest = commit_bump

        bullet = _format_bullet(summary)
        if not bullet:
            continue
        target_list = (
            secondary_bullets
            if commit_bump is None and commit_type in _NON_BUMP_TYPES
            else primary_bullets
        )
        if bullet not in primary_bullets and bullet not in secondary_bullets:
            target_list.append(bullet)

    bullets = [*primary_bullets, *secondary_bullets]
    return highest, bullets


def extract_changelog_bullets(changelog_text: str, version: str) -> list[str] | None:
    pattern = re.compile(
        rf"(?m)^##\s+v{re.escape(version)}(?:\s+\([^)\n]+\))?[ \t]*\n([\s\S]*?)(?=^##\s+|\Z)"
    )
    match = pattern.search(changelog_text)
    if match is None:
        return None
    bullets = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets or None


def prepend_changelog(
    changelog_text: str, version: str, release_date: str, bullets: list[str]
) -> str:
    if extract_changelog_bullets(changelog_text, version) is not None:
        return changelog_text
    if not bullets:
        raise ReleaseError("Cannot write an empty changelog section")
    section_lines = [f"## v{version} ({release_date})", ""]
    section_lines.extend(f"- {bullet}" for bullet in bullets)
    section = "\n".join(section_lines) + "\n\n"

    first_heading = re.search(r"(?m)^##\s+v\d+\.\d+\.\d+\b", changelog_text)
    if first_heading is None:
        suffix = "" if changelog_text.endswith("\n\n") else ("\n" if changelog_text.endswith("\n") else "\n\n")
        return changelog_text + suffix + section.rstrip("\n") + "\n"
    idx = first_heading.start()
    return changelog_text[:idx] + section + changelog_text[idx:]


def release_body(version: str, bullets: list[str]) -> str:
    lines = [f"# Veilleuse {version}", ""]
    lines.extend(f"- {bullet}" for bullet in bullets)
    return "\n".join(lines)


def _run(cmd: list[str], *, cwd: Path, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ReleaseError(f"Command failed ({' '.join(cmd)}): {detail}")
    return result


def _latest_semver_tag(repo: Path) -> str | None:
    res = _run(["git", "tag", "--merged", "HEAD", "--list", "v*"], cwd=repo)
    versions: list[tuple[tuple[int, int, int], str]] = []
    for raw in res.stdout.splitlines():
        tag = raw.strip()
        if not tag.startswith("v"):
            continue
        ver = tag[1:]
        try:
            parsed = parse_semver(ver)
        except ValueError:
            continue
        versions.append((parsed, ver))
    if not versions:
        return None
    versions.sort(key=lambda item: item[0])
    return versions[-1][1]


def _head_semver_tags(repo: Path) -> set[str]:
    res = _run(["git", "tag", "--points-at", "HEAD", "--list", "v*"], cwd=repo)
    out = set()
    for raw in res.stdout.splitlines():
        tag = raw.strip()
        if tag.startswith("v"):
            try:
                parse_semver(tag[1:])
                out.add(tag[1:])
            except ValueError:
                continue
    return out


def _commits_since(repo: Path, base_tag: str | None) -> list[tuple[str, str]]:
    rev_range = f"v{base_tag}..HEAD" if base_tag else "HEAD"
    res = _run(
        ["git", "log", "--reverse", "--format=%H%x1f%s%x1f%b%x1e", rev_range],
        cwd=repo,
    )
    commits: list[tuple[str, str]] = []
    for entry in res.stdout.split("\x1e"):
        record = entry.strip("\r\n")
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) >= 2:
            body = parts[2].strip() if len(parts) >= 3 else ""
            commits.append((parts[1].strip(), body))
    return commits


def plan_release(
    repo: Path = ROOT,
    *,
    bump_override: str | None = None,
    release_date: str | None = None,
) -> dict[str, object]:
    manifest_path = repo / "manifest.json"
    changelog_path = repo / "CHANGELOG.md"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ver = str(manifest.get("version", ""))
    manifest_tuple = parse_semver(manifest_ver)

    changelog_text = changelog_path.read_text(encoding="utf-8")
    last_tag_ver = _latest_semver_tag(repo)
    head_tags = _head_semver_tags(repo)
    head_subject = _run(["git", "log", "-1", "--format=%s", "HEAD"], cwd=repo).stdout.strip()
    release_commit_match = _RELEASE_COMMIT_RE.match(head_subject)
    date_str = release_date or datetime.date.today().isoformat()

    if manifest_ver in head_tags or (
        release_commit_match and release_commit_match.group("version") == manifest_ver
    ):
        bullets = extract_changelog_bullets(changelog_text, manifest_ver) or [
            f"Release Veilleuse {manifest_ver}."
        ]
        return {
            "action": "ensure_tag_and_release",
            "previous_version": last_tag_ver,
            "target_version": manifest_ver,
            "tag": f"v{manifest_ver}",
            "title": f"Veilleuse {manifest_ver}",
            "date": date_str,
            "bullets": bullets,
            "body": release_body(manifest_ver, bullets),
            "needs_commit": False,
            "needs_tag": manifest_ver not in head_tags,
        }

    commits = _commits_since(repo, last_tag_ver)
    inferred_bump, commit_bullets = classify_commits(commits)

    if last_tag_ver is not None and manifest_tuple > parse_semver(last_tag_ver):
        target_ver = manifest_ver
        bullets = (
            extract_changelog_bullets(changelog_text, target_ver)
            or commit_bullets
            or [f"Release Veilleuse {target_ver}."]
        )
        return {
            "action": "release",
            "previous_version": last_tag_ver,
            "target_version": target_ver,
            "tag": f"v{target_ver}",
            "title": f"Veilleuse {target_ver}",
            "date": date_str,
            "bullets": bullets,
            "body": release_body(target_ver, bullets),
            "needs_commit": extract_changelog_bullets(changelog_text, target_ver) is None,
            "needs_tag": True,
        }

    effective_bump = bump_override or inferred_bump
    if effective_bump is None:
        return {
            "action": "skip_no_releasable_commits",
            "previous_version": last_tag_ver or manifest_ver,
            "target_version": None,
            "tag": None,
            "title": None,
            "date": date_str,
            "bullets": [],
            "body": "",
            "needs_commit": False,
            "needs_tag": False,
        }

    base_ver = last_tag_ver or manifest_ver
    target_ver = bump_semver(base_ver, effective_bump)
    bullets = (
        extract_changelog_bullets(changelog_text, target_ver)
        or commit_bullets
        or [f"Release Veilleuse {target_ver}."]
    )
    return {
        "action": "release",
        "previous_version": base_ver,
        "target_version": target_ver,
        "tag": f"v{target_ver}",
        "title": f"Veilleuse {target_ver}",
        "date": date_str,
        "bullets": bullets,
        "body": release_body(target_ver, bullets),
        "needs_commit": True,
        "needs_tag": True,
    }


def apply_release(
    repo: Path = ROOT,
    *,
    bump_override: str | None = None,
    release_date: str | None = None,
    push: bool = False,
) -> dict[str, object]:
    status = _run(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    if status:
        raise ReleaseError(f"Working tree must be clean before cutting a release:\n{status}")

    plan = plan_release(repo, bump_override=bump_override, release_date=release_date)
    action = plan["action"]
    if action == "skip_no_releasable_commits":
        return plan

    target_ver = str(plan["target_version"])
    tag = str(plan["tag"])
    title = str(plan["title"])
    body = str(plan["body"])
    bullets = list(plan["bullets"])  # type: ignore[arg-type]
    date_str = str(plan["date"])

    git_id = [
        "-c", f"user.name={GIT_AUTHOR_NAME}",
        "-c", f"user.email={GIT_AUTHOR_EMAIL}",
    ]

    if plan["needs_commit"]:
        manifest_path = repo / "manifest.json"
        changelog_path = repo / "CHANGELOG.md"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = target_ver
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        updated_changelog = prepend_changelog(
            changelog_path.read_text(encoding="utf-8"),
            target_ver,
            date_str,
            bullets,
        )
        changelog_path.write_text(updated_changelog, encoding="utf-8")

        hygiene = repo / "scripts" / "check_hygiene.sh"
        if hygiene.is_file():
            _run([str(hygiene), str(repo)], cwd=repo)

        _run(["git", "add", "manifest.json", "CHANGELOG.md"], cwd=repo)
        _run(
            ["git", *git_id, "commit", "-m", f"chore(release): prepare {tag}"],
            cwd=repo,
        )

    existing_tag = _run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=repo, check=False)
    if existing_tag.returncode != 0:
        _run(["git", *git_id, "tag", "-a", tag, "-m", title], cwd=repo)

    published = False
    if push:
        if plan["needs_commit"]:
            _run(["git", "push", "origin", "HEAD:refs/heads/main"], cwd=repo)
        head_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        tag_push = _run(["git", "push", "origin", f"refs/tags/{tag}"], cwd=repo, check=False)
        view = _run(["gh", "release", "view", tag], cwd=repo, check=False)
        if view.returncode != 0:
            _run(
                [
                    "gh", "release", "create", tag,
                    "--target", head_sha,
                    "--title", title,
                    "--notes-file", "-",
                ],
                cwd=repo,
                input_text=body + "\n",
            )
            published = True
        elif tag_push.returncode != 0:
            remote_tag = _run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], cwd=repo)
            if not remote_tag.stdout.strip():
                detail = (tag_push.stderr or tag_push.stdout or "").strip()
                raise ReleaseError(f"Command failed (git push origin refs/tags/{tag}): {detail}")

    return {**plan, "committed": bool(plan["needs_commit"]), "published": published}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Compute release plan without mutating state")
    mode.add_argument("--apply", action="store_true", help="Write manifest/changelog, commit, and tag")
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push release commit/tag to origin and create the GitHub Release (requires --apply)",
    )
    parser.add_argument(
        "--bump",
        choices=("patch", "minor", "major"),
        default=None,
        help="Explicit SemVer bump override",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Override YYYY-MM-DD changelog date",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.push and not args.apply:
        sys.stderr.write("--push requires --apply\n")
        return 2
    try:
        if args.apply:
            outcome = apply_release(
                ROOT,
                bump_override=args.bump,
                release_date=args.date,
                push=args.push,
            )
        else:
            outcome = plan_release(
                ROOT,
                bump_override=args.bump,
                release_date=args.date,
            )
    except (ReleaseError, ValueError, OSError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    json.dump({"ok": True, **outcome}, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
