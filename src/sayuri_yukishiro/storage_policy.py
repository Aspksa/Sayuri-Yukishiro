from __future__ import annotations

import ctypes
import os
from pathlib import Path

_ALLOWED_JOURNAL_MODES = {"WAL", "DELETE"}


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _is_synced_path(path: Path) -> bool:
    candidates = [
        os.environ.get("OneDrive"),
        os.environ.get("OneDriveCommercial"),
        os.environ.get("OneDriveConsumer"),
    ]
    for raw in candidates:
        if raw and _is_under(path, Path(raw)):
            return True
    return any(part.casefold().startswith("onedrive") for part in path.parts)


def _windows_drive_type(path: Path) -> int | None:
    if os.name != "nt":
        return None
    anchor = path.resolve(strict=False).anchor
    if not anchor:
        return None
    try:
        return int(ctypes.windll.kernel32.GetDriveTypeW(str(anchor)))
    except Exception:
        return None


def sqlite_journal_mode(path: Path) -> str:
    override = os.environ.get("SAYURI_SQLITE_JOURNAL_MODE", "").strip().upper()
    if override:
        if override not in _ALLOWED_JOURNAL_MODES:
            raise ValueError(
                "SAYURI_SQLITE_JOURNAL_MODE must be WAL or DELETE"
            )
        return override

    resolved = path.resolve(strict=False)
    text = str(resolved)
    if text.startswith("\\") or text.startswith("//"):
        return "DELETE"
    if _is_synced_path(resolved):
        return "DELETE"

    drive_type = _windows_drive_type(resolved)
    if drive_type in {2, 4}:
        return "DELETE"

    return "WAL"
