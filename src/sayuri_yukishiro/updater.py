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


def safe_update() -> UpdateResult:
    if not shutil.which("git"):
        return UpdateResult("unavailable", "Git is not installed; automatic Git update skipped.")

    inside = _git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return UpdateResult("unavailable", "This copy is not a Git worktree; update skipped.")

    remote_proc = _git("remote", "get-url", "origin")
    remote = remote_proc.stdout.strip() if remote_proc.returncode == 0 else None

    dirty = _git("status", "--porcelain")
    if dirty.returncode != 0:
        return UpdateResult("error", "Unable to inspect Git worktree.", remote=remote)
    if dirty.stdout.strip():
        return UpdateResult(
            "skipped",
            "Local changes are present; automatic update was not applied.",
            remote=remote,
        )

    before_proc = _git("rev-parse", "HEAD")
    before = before_proc.stdout.strip() if before_proc.returncode == 0 else None

    fetch = _git("fetch", "--quiet", "origin", "main", timeout=60)
    if fetch.returncode != 0:
        message = fetch.stderr.strip() or "Git fetch failed."
        return UpdateResult("error", message, before=before, remote=remote)

    upstream_proc = _git("rev-parse", "origin/main")
    if upstream_proc.returncode != 0:
        return UpdateResult("error", "origin/main cannot be resolved.", before=before, remote=remote)
    upstream = upstream_proc.stdout.strip()

    if before == upstream:
        return UpdateResult("up_to_date", "Already up to date.", before=before, after=before, remote=remote)

    ancestor = _git("merge-base", "--is-ancestor", before or "HEAD", upstream)
    if ancestor.returncode != 0:
        return UpdateResult(
            "skipped",
            "Local history diverges from origin/main; automatic update refused.",
            before=before,
            remote=remote,
        )

    merge = _git("merge", "--ff-only", "--quiet", upstream, timeout=60)
    if merge.returncode != 0:
        message = merge.stderr.strip() or "Fast-forward update failed."
        return UpdateResult("error", message, before=before, remote=remote)

    after_proc = _git("rev-parse", "HEAD")
    after = after_proc.stdout.strip() if after_proc.returncode == 0 else upstream
    return UpdateResult("updated", "Updated safely from origin/main.", before=before, after=after, remote=remote)
