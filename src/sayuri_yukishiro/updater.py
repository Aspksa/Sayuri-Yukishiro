from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass

from .paths import PROJECT_ROOT


@dataclass
class UpdateResult:
    status: str
    message: str
    before: str | None = None
    after: str | None = None
    remote: str | None = None
    upstream: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _git(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _resolve_upstream() -> tuple[str, str, str] | None:
    branch_proc = _git("symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_proc.returncode != 0 or not branch_proc.stdout.strip():
        return None

    upstream_proc = _git(
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    )
    if upstream_proc.returncode != 0:
        return None

    upstream = upstream_proc.stdout.strip()
    if "/" not in upstream:
        return None
    remote_name, remote_branch = upstream.split("/", 1)
    if not remote_name or not remote_branch:
        return None
    return remote_name, remote_branch, upstream


def safe_update() -> UpdateResult:
    if not shutil.which("git"):
        return UpdateResult("unavailable", "Git is not installed; automatic Git update skipped.")

    inside = _git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return UpdateResult("unavailable", "This copy is not a Git worktree; update skipped.")

    resolved = _resolve_upstream()
    if resolved is None:
        return UpdateResult(
            "skipped",
            "Current branch is detached or has no configured upstream; automatic update skipped.",
        )
    remote_name, remote_branch, upstream_ref = resolved

    remote_proc = _git("remote", "get-url", remote_name)
    remote = remote_proc.stdout.strip() if remote_proc.returncode == 0 else None

    dirty = _git("status", "--porcelain")
    if dirty.returncode != 0:
        return UpdateResult(
            "error",
            "Unable to inspect Git worktree.",
            remote=remote,
            upstream=upstream_ref,
        )
    if dirty.stdout.strip():
        return UpdateResult(
            "skipped",
            "Local changes are present; automatic update was not applied.",
            remote=remote,
            upstream=upstream_ref,
        )

    before_proc = _git("rev-parse", "HEAD")
    before = before_proc.stdout.strip() if before_proc.returncode == 0 else None

    fetch = _git("fetch", "--quiet", remote_name, remote_branch, timeout=60)
    if fetch.returncode != 0:
        message = fetch.stderr.strip() or "Git fetch failed."
        return UpdateResult(
            "error",
            message,
            before=before,
            remote=remote,
            upstream=upstream_ref,
        )

    upstream_proc = _git("rev-parse", upstream_ref)
    if upstream_proc.returncode != 0:
        return UpdateResult(
            "error",
            f"{upstream_ref} cannot be resolved.",
            before=before,
            remote=remote,
            upstream=upstream_ref,
        )
    upstream_sha = upstream_proc.stdout.strip()

    if before == upstream_sha:
        return UpdateResult(
            "up_to_date",
            f"Already up to date with {upstream_ref}.",
            before=before,
            after=before,
            remote=remote,
            upstream=upstream_ref,
        )

    ancestor = _git("merge-base", "--is-ancestor", before or "HEAD", upstream_sha)
    if ancestor.returncode != 0:
        return UpdateResult(
            "skipped",
            f"Local history diverges from {upstream_ref}; automatic update refused.",
            before=before,
            remote=remote,
            upstream=upstream_ref,
        )

    merge = _git("merge", "--ff-only", "--quiet", upstream_sha, timeout=60)
    if merge.returncode != 0:
        message = merge.stderr.strip() or "Fast-forward update failed."
        return UpdateResult(
            "error",
            message,
            before=before,
            remote=remote,
            upstream=upstream_ref,
        )

    after_proc = _git("rev-parse", "HEAD")
    after = after_proc.stdout.strip() if after_proc.returncode == 0 else upstream_sha
    return UpdateResult(
        "updated",
        f"Updated safely from {upstream_ref}.",
        before=before,
        after=after,
        remote=remote,
        upstream=upstream_ref,
    )
