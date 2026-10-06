from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import PROJECT_ROOT


@dataclass(frozen=True)
class UpstreamInfo:
    branch: str
    remote_name: str
    remote_branch: str
    upstream_ref: str
    remote_url: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class UpdateInspection:
    status: str
    message: str
    current_sha: str | None = None
    target_sha: str | None = None
    current_version: str | None = None
    available_version: str | None = None
    dirty: bool = False
    diverged: bool = False
    upstream: UpstreamInfo | None = None
    changes: tuple[str, ...] = ()

    @property
    def update_available(self) -> bool:
        return self.status == "available"

    @property
    def can_apply(self) -> bool:
        return self.update_available and not self.dirty and not self.diverged

    def to_dict(self) -> dict:
        data = asdict(self)
        data["update_available"] = self.update_available
        data["can_apply"] = self.can_apply
        return data


def run_git(
    *args: str,
    timeout: int = 30,
    root: Path = PROJECT_ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def resolve_upstream(root: Path = PROJECT_ROOT) -> UpstreamInfo | None:
    branch_proc = run_git(
        "symbolic-ref", "--quiet", "--short", "HEAD", root=root
    )
    if branch_proc.returncode != 0 or not branch_proc.stdout.strip():
        return None
    branch = branch_proc.stdout.strip()

    upstream_proc = run_git(
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        root=root,
    )
    if upstream_proc.returncode != 0:
        return None

    upstream_ref = upstream_proc.stdout.strip()
    if "/" not in upstream_ref:
        return None
    remote_name, remote_branch = upstream_ref.split("/", 1)
    if not remote_name or not remote_branch:
        return None

    remote_proc = run_git("remote", "get-url", remote_name, root=root)
    remote_url = (
        remote_proc.stdout.strip() if remote_proc.returncode == 0 else None
    )
    return UpstreamInfo(
        branch=branch,
        remote_name=remote_name,
        remote_branch=remote_branch,
        upstream_ref=upstream_ref,
        remote_url=remote_url,
    )


def _version_at(ref: str, root: Path) -> str | None:
    proc = run_git("show", f"{ref}:VERSION", root=root)
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def _changes_between(
    current_sha: str,
    target_sha: str,
    root: Path,
    limit: int = 100,
) -> tuple[str, ...]:
    proc = run_git(
        "log",
        "--reverse",
        "--format=%h %s",
        f"{current_sha}..{target_sha}",
        root=root,
    )
    if proc.returncode != 0:
        return ()
    lines = tuple(
        line.strip() for line in proc.stdout.splitlines() if line.strip()
    )
    return lines[: max(1, limit)]


def _fetch_tracking_ref(
    upstream: UpstreamInfo,
    root: Path,
) -> subprocess.CompletedProcess[str]:
    refspec = (
        f"+refs/heads/{upstream.remote_branch}:"
        f"refs/remotes/{upstream.remote_name}/{upstream.remote_branch}"
    )
    return run_git(
        "fetch",
        "--quiet",
        upstream.remote_name,
        refspec,
        timeout=60,
        root=root,
    )


def inspect_update(
    *,
    fetch: bool = True,
    root: Path = PROJECT_ROOT,
) -> UpdateInspection:
    if not shutil.which("git"):
        return UpdateInspection(
            "unavailable",
            "Git is not installed; update check is unavailable.",
        )

    inside = run_git("rev-parse", "--is-inside-work-tree", root=root)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return UpdateInspection(
            "unavailable",
            "This copy is not a Git worktree.",
        )

    upstream = resolve_upstream(root)
    if upstream is None:
        return UpdateInspection(
            "blocked",
            "Current branch is detached or has no configured upstream.",
        )

    dirty_proc = run_git("status", "--porcelain", root=root)
    if dirty_proc.returncode != 0:
        return UpdateInspection(
            "error",
            "Unable to inspect Git worktree.",
            upstream=upstream,
        )
    dirty = bool(dirty_proc.stdout.strip())

    current_proc = run_git("rev-parse", "HEAD", root=root)
    if current_proc.returncode != 0:
        return UpdateInspection(
            "error",
            "Unable to resolve current HEAD.",
            dirty=dirty,
            upstream=upstream,
        )
    current_sha = current_proc.stdout.strip()

    if fetch:
        fetched = _fetch_tracking_ref(upstream, root)
        if fetched.returncode != 0:
            return UpdateInspection(
                "error",
                fetched.stderr.strip() or "Git fetch failed.",
                current_sha=current_sha,
                current_version=_version_at(current_sha, root),
                dirty=dirty,
                upstream=upstream,
            )

    target_proc = run_git("rev-parse", upstream.upstream_ref, root=root)
    if target_proc.returncode != 0:
        return UpdateInspection(
            "error",
            f"{upstream.upstream_ref} cannot be resolved.",
            current_sha=current_sha,
            current_version=_version_at(current_sha, root),
            dirty=dirty,
            upstream=upstream,
        )
    target_sha = target_proc.stdout.strip()
    current_version = _version_at(current_sha, root)
    available_version = _version_at(target_sha, root)

    if current_sha == target_sha:
        return UpdateInspection(
            "up_to_date",
            "Project is already up to date.",
            current_sha=current_sha,
            target_sha=target_sha,
            current_version=current_version,
            available_version=available_version,
            dirty=dirty,
            upstream=upstream,
        )

    ancestor = run_git(
        "merge-base",
        "--is-ancestor",
        current_sha,
        target_sha,
        root=root,
    )
    diverged = ancestor.returncode != 0
    if diverged:
        return UpdateInspection(
            "diverged",
            "Local history diverges from upstream; automatic update refused.",
            current_sha=current_sha,
            target_sha=target_sha,
            current_version=current_version,
            available_version=available_version,
            dirty=dirty,
            diverged=True,
            upstream=upstream,
        )

    changes = _changes_between(current_sha, target_sha, root)
    message = (
        "Update is available but local changes must be resolved first."
        if dirty
        else "Update is available."
    )
    return UpdateInspection(
        "available",
        message,
        current_sha=current_sha,
        target_sha=target_sha,
        current_version=current_version,
        available_version=available_version,
        dirty=dirty,
        upstream=upstream,
        changes=changes,
    )
