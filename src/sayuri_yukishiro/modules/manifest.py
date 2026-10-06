from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "module.json"
MANIFEST_SCHEMA_VERSION = 1

MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}(\.[a-z][a-z0-9_]{0,63})*$")
SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VERSION_SPEC_PATTERN = re.compile(r"^(>=|==|~>)(\d+)\.(\d+)\.(\d+)$")

ALLOWED_RISKS = ("read_only", "mutation", "external")
ALLOWED_PERMISSIONS = (
    "core.config.read",
    "core.events.publish",
    "core.jobs.submit",
    "core.checkpoints.write",
    "module.database",
    "system.process",
    "network.outbound",
    "filesystem.write",
)
AUTO_GRANTED_PERMISSIONS = (
    "core.config.read",
    "core.events.publish",
    "core.jobs.submit",
    "core.checkpoints.write",
    "module.database",
)


class ManifestError(ValueError):
    """Манифест модуля не соответствует обязательному формату."""


@dataclass(frozen=True)
class VersionSpec:
    """Требование к версии зависимости: >=X.Y.Z, ==X.Y.Z или ~>X.Y.Z."""

    operator: str
    version: tuple[int, int, int]

    @classmethod
    def parse(cls, raw: str) -> "VersionSpec":
        text = str(raw).strip().replace(" ", "")
        if SEMVER_PATTERN.fullmatch(text):
            text = f">={text}"
        match = VERSION_SPEC_PATTERN.fullmatch(text)
        if match is None:
            raise ManifestError(
                f"Invalid version requirement: {raw!r}. Use >=X.Y.Z, ==X.Y.Z or ~>X.Y.Z."
            )
        operator = match.group(1)
        version = (int(match.group(2)), int(match.group(3)), int(match.group(4)))
        return cls(operator=operator, version=version)

    def matches(self, version: str) -> bool:
        actual = parse_semver(version)
        if self.operator == "==":
            return actual == self.version
        if self.operator == ">=":
            return actual >= self.version
        return (
            actual >= self.version
            and actual[0] == self.version[0]
            and actual[1] == self.version[1]
        )

    def to_text(self) -> str:
        major, minor, patch = self.version
        return f"{self.operator}{major}.{minor}.{patch}"


def parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(str(version).strip())
    if match is None:
        raise ManifestError(f"Invalid semantic version: {version!r}. Use MAJOR.MINOR.PATCH.")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


@dataclass(frozen=True)
class CapabilityDeclaration:
    name: str
    risk: str
    handler: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "risk": self.risk,
            "handler": self.handler,
            "description": self.description,
        }


@dataclass(frozen=True)
class DependencyDeclaration:
    module_id: str
    requirement: VersionSpec

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.module_id, "version": self.requirement.to_text()}


@dataclass(frozen=True)
class ModuleManifest:
    id: str
    name: str
    version: str
    entry_point: str
    description: str = ""
    enabled: bool = True
    requires_core: VersionSpec | None = None
    dependencies: tuple[DependencyDeclaration, ...] = ()
    permissions: tuple[str, ...] = ()
    capabilities: tuple[CapabilityDeclaration, ...] = ()
    schema_version: int = 0
    source: Path | None = None

    @property
    def directory(self) -> Path | None:
        return None if self.source is None else self.source.parent

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "entry_point": self.entry_point,
            "description": self.description,
            "enabled": self.enabled,
            "requires_core": None if self.requires_core is None else self.requires_core.to_text(),
            "dependencies": [item.to_dict() for item in self.dependencies],
            "permissions": list(self.permissions),
            "capabilities": [item.to_dict() for item in self.capabilities],
            "schema_version": self.schema_version,
            "source": None if self.source is None else str(self.source),
        }


@dataclass(frozen=True)
class ManifestRejection:
    source: str
    error: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "error": self.error}


@dataclass
class ManifestScan:
    manifests: list[ModuleManifest] = field(default_factory=list)
    rejected: list[ManifestRejection] = field(default_factory=list)


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"Field {key!r} is required and must be a non-empty string")
    return value.strip()


def _parse_capabilities(raw: Any) -> tuple[CapabilityDeclaration, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("Field 'capabilities' must be a list")

    capabilities: list[CapabilityDeclaration] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ManifestError("Every capability must be an object")
        name = _require_str(item, "name")
        if not CAPABILITY_NAME_PATTERN.fullmatch(name):
            raise ManifestError(
                f"Invalid capability name: {name!r}. Use lowercase words separated by dots."
            )
        if name in seen:
            raise ManifestError(f"Duplicate capability declaration: {name}")
        seen.add(name)
        risk = _require_str(item, "risk").lower()
        if risk not in ALLOWED_RISKS:
            raise ManifestError(
                f"Invalid risk {risk!r} for capability {name!r}. Allowed: {', '.join(ALLOWED_RISKS)}."
            )
        handler = _require_str(item, "handler")
        description = item.get("description", "")
        if not isinstance(description, str):
            raise ManifestError(f"Capability {name!r} description must be a string")
        capabilities.append(
            CapabilityDeclaration(
                name=name,
                risk=risk,
                handler=handler,
                description=description.strip(),
            )
        )
    return tuple(capabilities)


def _parse_dependencies(raw: Any, own_id: str) -> tuple[DependencyDeclaration, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("Field 'dependencies' must be a list")

    dependencies: list[DependencyDeclaration] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ManifestError("Every dependency must be an object with 'id' and 'version'")
        module_id = _require_str(item, "id")
        if not MODULE_ID_PATTERN.fullmatch(module_id):
            raise ManifestError(f"Invalid dependency id: {module_id!r}")
        if module_id == own_id:
            raise ManifestError(f"Module {own_id!r} must not depend on itself")
        if module_id in seen:
            raise ManifestError(f"Duplicate dependency: {module_id}")
        seen.add(module_id)
        dependencies.append(
            DependencyDeclaration(
                module_id=module_id,
                requirement=VersionSpec.parse(_require_str(item, "version")),
            )
        )
    return tuple(dependencies)


def _parse_permissions(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("Field 'permissions' must be a list")

    permissions: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ManifestError("Every permission must be a non-empty string")
        permission = item.strip()
        if permission not in ALLOWED_PERMISSIONS:
            raise ManifestError(
                f"Unknown permission: {permission!r}. Allowed: {', '.join(ALLOWED_PERMISSIONS)}."
            )
        if permission not in permissions:
            permissions.append(permission)
    return tuple(permissions)


def parse_manifest(data: dict[str, Any], source: Path | None = None) -> ModuleManifest:
    if not isinstance(data, dict):
        raise ManifestError("Manifest root must be an object")

    declared_schema = data.get("manifest_version", MANIFEST_SCHEMA_VERSION)
    if not isinstance(declared_schema, int) or isinstance(declared_schema, bool):
        raise ManifestError("Field 'manifest_version' must be an integer")
    if declared_schema != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"Unsupported manifest_version {declared_schema}; expected {MANIFEST_SCHEMA_VERSION}"
        )

    module_id = _require_str(data, "id")
    if not MODULE_ID_PATTERN.fullmatch(module_id):
        raise ManifestError(
            f"Invalid module id: {module_id!r}. Use lowercase letters, digits and underscore."
        )

    version = _require_str(data, "version")
    parse_semver(version)

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ManifestError("Field 'enabled' must be a boolean")

    schema_version = data.get("schema_version", 0)
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 0:
        raise ManifestError("Field 'schema_version' must be a non-negative integer")

    description = data.get("description", "")
    if not isinstance(description, str):
        raise ManifestError("Field 'description' must be a string")

    requires_core_raw = data.get("requires_core")
    requires_core = (
        VersionSpec.parse(requires_core_raw) if isinstance(requires_core_raw, str) else None
    )
    if requires_core_raw is not None and requires_core is None:
        raise ManifestError("Field 'requires_core' must be a version requirement string")

    return ModuleManifest(
        id=module_id,
        name=_require_str(data, "name"),
        version=version,
        entry_point=_require_str(data, "entry_point"),
        description=description.strip(),
        enabled=enabled,
        requires_core=requires_core,
        dependencies=_parse_dependencies(data.get("dependencies"), module_id),
        permissions=_parse_permissions(data.get("permissions")),
        capabilities=_parse_capabilities(data.get("capabilities")),
        schema_version=schema_version,
        source=None if source is None else source.resolve(),
    )


def load_manifest(path: Path) -> ModuleManifest:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"Manifest is not readable: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest is not valid JSON: {exc}") from exc
    return parse_manifest(data, source=path)
