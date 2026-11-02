from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .general import CATVariant, Variant

if TYPE_CHECKING:
    from .service import (
        ApplicationService,
        EditorService,
        application_service_types,
        editor_service_types,
    )

_SERVICE_EXPORTS = frozenset({
    "ApplicationService",
    "EditorService",
    "application_service_types",
    "editor_service_types",
})


def __getattr__(name: str) -> Any:
    if name in _SERVICE_EXPORTS:
        from . import service as _service_mod

        val = getattr(_service_mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ApplicationService",
    "CATVariant",
    "EditorService",
    "Variant",
    "application_service_types",
    "editor_service_types",
]
