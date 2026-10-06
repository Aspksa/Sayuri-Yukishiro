"""Sayuri Yukishiro package."""

from .version import COGNITIVE_CORE_VERSION, PROJECT_VERSION, SYSTEM_CORE_VERSION

__version__ = PROJECT_VERSION
CORE_VERSION = SYSTEM_CORE_VERSION

__all__ = [
    "__version__",
    "CORE_VERSION",
    "COGNITIVE_CORE_VERSION",
]
