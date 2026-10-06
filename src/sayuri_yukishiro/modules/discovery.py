from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ManifestRejection,
    ModuleManifest,
    load_manifest,
)


@dataclass
class DiscoveryResult:
    """Результат обхода каталогов модулей."""

    manifests: list[ModuleManifest] = field(default_factory=list)
    rejected: list[ManifestRejection] = field(default_factory=list)
    scanned_dirs: list[str] = field(default_factory=list)

    def by_id(self) -> dict[str, ModuleManifest]:
        return {manifest.id: manifest for manifest in self.manifests}

    def to_dict(self) -> dict[str, object]:
        return {
            "scanned_dirs": list(self.scanned_dirs),
            "discovered": [manifest.id for manifest in self.manifests],
            "rejected": [item.to_dict() for item in self.rejected],
        }


def discover_modules(directories: list[Path]) -> DiscoveryResult:
    """Найти манифесты модулей.

    Ошибка одного манифеста не отменяет обнаружение остальных: такой модуль
    попадает в rejected с причиной, а рантайм продолжает работу.
    """

    result = DiscoveryResult()
    seen: dict[str, ModuleManifest] = {}

    for directory in directories:
        result.scanned_dirs.append(str(directory))
        if not directory.is_dir():
            continue

        for candidate in sorted(directory.iterdir(), key=lambda item: item.name):
            if not candidate.is_dir() or candidate.name.startswith((".", "_")):
                continue

            manifest_path = candidate / MANIFEST_FILENAME
            if not manifest_path.is_file():
                result.rejected.append(
                    ManifestRejection(
                        source=str(candidate),
                        error=f"{MANIFEST_FILENAME} not found",
                    )
                )
                continue

            try:
                manifest = load_manifest(manifest_path)
            except ManifestError as exc:
                result.rejected.append(
                    ManifestRejection(source=str(manifest_path), error=str(exc))
                )
                continue

            if manifest.id != candidate.name:
                result.rejected.append(
                    ManifestRejection(
                        source=str(manifest_path),
                        error=(
                            f"Manifest id {manifest.id!r} does not match "
                            f"directory name {candidate.name!r}"
                        ),
                    )
                )
                continue

            existing = seen.get(manifest.id)
            if existing is not None:
                result.rejected.append(
                    ManifestRejection(
                        source=str(manifest_path),
                        error=(
                            f"Duplicate module id {manifest.id!r}; already loaded from "
                            f"{existing.source}"
                        ),
                    )
                )
                continue

            seen[manifest.id] = manifest
            result.manifests.append(manifest)

    result.manifests.sort(key=lambda manifest: manifest.id)
    return result
