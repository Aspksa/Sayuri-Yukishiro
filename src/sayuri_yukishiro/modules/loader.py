from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from .base import ModuleContext, SayuriModule
from .manifest import ModuleManifest

ENTRY_POINT_PATTERN = re.compile(
    r"^([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*):([A-Za-z_][A-Za-z0-9_]*)$"
)


class ModuleLoadError(RuntimeError):
    """Модуль не удалось загрузить по его entry_point."""


def _resolve_entry_file(manifest: ModuleManifest) -> tuple[Path, str]:
    match = ENTRY_POINT_PATTERN.fullmatch(manifest.entry_point)
    if match is None:
        raise ModuleLoadError(
            f"Invalid entry_point {manifest.entry_point!r}. Use '<python_module>:<ClassName>'."
        )

    directory = manifest.directory
    if directory is None:
        raise ModuleLoadError("Manifest has no source directory")

    relative = Path(*match.group(1).split("."))
    candidates = (
        directory / f"{relative}.py",
        directory / relative / "__init__.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            resolved = candidate.resolve()
            if directory.resolve() not in resolved.parents:
                raise ModuleLoadError(
                    f"entry_point escapes the module directory: {resolved}"
                )
            return resolved, match.group(2)

    raise ModuleLoadError(
        f"entry_point file not found for {manifest.entry_point!r} in {directory}"
    )


def load_module_class(manifest: ModuleManifest) -> type[SayuriModule]:
    """Загрузить класс модуля из его каталога без правки sys.path."""

    path, class_name = _resolve_entry_file(manifest)
    import_name = f"sayuri_module_{manifest.id}"

    spec = importlib.util.spec_from_file_location(import_name, path)
    if spec is None or spec.loader is None:
        raise ModuleLoadError(f"Python module is not importable: {path}")

    python_module = importlib.util.module_from_spec(spec)
    sys.modules[import_name] = python_module
    try:
        spec.loader.exec_module(python_module)
    except Exception as exc:
        sys.modules.pop(import_name, None)
        raise ModuleLoadError(f"entry_point import failed: {exc}") from exc

    target = getattr(python_module, class_name, None)
    if target is None:
        raise ModuleLoadError(f"Class {class_name!r} not found in {path}")
    if not (isinstance(target, type) and issubclass(target, SayuriModule)):
        raise ModuleLoadError(f"Class {class_name!r} must inherit from SayuriModule")
    return target


def instantiate_module(
    manifest: ModuleManifest,
    context: ModuleContext,
) -> SayuriModule:
    module_class = load_module_class(manifest)
    try:
        instance = module_class(context)
    except Exception as exc:
        raise ModuleLoadError(f"Module constructor failed: {exc}") from exc
    return instance


def unload_module(manifest: ModuleManifest) -> None:
    sys.modules.pop(f"sayuri_module_{manifest.id}", None)
