from __future__ import annotations

from dataclasses import dataclass, field

from .manifest import ModuleManifest


@dataclass(frozen=True)
class DependencyIssue:
    module_id: str
    reason: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"module_id": self.module_id, "reason": self.reason, "detail": self.detail}


@dataclass
class ResolutionResult:
    """Разрешённый порядок запуска и причины отказов."""

    order: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    issues: list[DependencyIssue] = field(default_factory=list)

    def issue_for(self, module_id: str) -> DependencyIssue | None:
        for issue in self.issues:
            if issue.module_id == module_id:
                return issue
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "order": list(self.order),
            "disabled": list(self.disabled),
            "issues": [issue.to_dict() for issue in self.issues],
        }


class DependencyResolver:
    """Строит детерминированный порядок запуска модулей.

    Отклоняются модули с несовместимым требованием к ядру, с отсутствующими,
    отключёнными или несовместимыми по версии зависимостями, а также любые
    модули, попавшие в цикл зависимостей.
    """

    def resolve(
        self,
        manifests: list[ModuleManifest],
        *,
        core_version: str,
    ) -> ResolutionResult:
        result = ResolutionResult()
        catalog = {manifest.id: manifest for manifest in manifests}

        enabled: dict[str, ModuleManifest] = {}
        for module_id in sorted(catalog):
            manifest = catalog[module_id]
            if not manifest.enabled:
                result.disabled.append(module_id)
                continue
            enabled[module_id] = manifest

        rejected: dict[str, DependencyIssue] = {}

        for module_id in sorted(enabled):
            manifest = enabled[module_id]
            if manifest.requires_core is not None and not manifest.requires_core.matches(
                core_version
            ):
                rejected[module_id] = DependencyIssue(
                    module_id,
                    "incompatible_core",
                    (
                        f"requires core {manifest.requires_core.to_text()}, "
                        f"runtime core is {core_version}"
                    ),
                )
                continue

            for dependency in manifest.dependencies:
                target = catalog.get(dependency.module_id)
                if target is None:
                    rejected[module_id] = DependencyIssue(
                        module_id,
                        "missing_dependency",
                        f"{dependency.module_id} is not installed",
                    )
                    break
                if not target.enabled:
                    rejected[module_id] = DependencyIssue(
                        module_id,
                        "dependency_disabled",
                        f"{dependency.module_id} is disabled",
                    )
                    break
                if not dependency.requirement.matches(target.version):
                    rejected[module_id] = DependencyIssue(
                        module_id,
                        "incompatible_dependency",
                        (
                            f"{dependency.module_id} {target.version} does not satisfy "
                            f"{dependency.requirement.to_text()}"
                        ),
                    )
                    break

        candidates = {
            module_id: manifest
            for module_id, manifest in enabled.items()
            if module_id not in rejected
        }

        # Каскад: модуль нельзя запускать, если отклонена любая его зависимость.
        changed = True
        while changed:
            changed = False
            for module_id in sorted(candidates):
                manifest = candidates[module_id]
                for dependency in manifest.dependencies:
                    if dependency.module_id in rejected:
                        rejected[module_id] = DependencyIssue(
                            module_id,
                            "dependency_unresolved",
                            f"{dependency.module_id} is not startable",
                        )
                        del candidates[module_id]
                        changed = True
                        break
                if changed:
                    break

        order = self._topological_order(candidates)
        unordered = sorted(set(candidates) - set(order))
        for module_id in unordered:
            rejected[module_id] = DependencyIssue(
                module_id,
                "dependency_cycle",
                "module participates in a dependency cycle",
            )

        result.order = order
        result.issues = [rejected[module_id] for module_id in sorted(rejected)]
        return result

    @staticmethod
    def _topological_order(candidates: dict[str, ModuleManifest]) -> list[str]:
        remaining = {
            module_id: {
                dependency.module_id
                for dependency in manifest.dependencies
                if dependency.module_id in candidates
            }
            for module_id, manifest in candidates.items()
        }

        order: list[str] = []
        while remaining:
            ready = sorted(
                module_id for module_id, deps in remaining.items() if not deps
            )
            if not ready:
                break
            for module_id in ready:
                order.append(module_id)
                del remaining[module_id]
            for deps in remaining.values():
                deps.difference_update(ready)
        return order
