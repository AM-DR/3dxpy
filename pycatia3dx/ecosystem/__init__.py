"""
Full 3DEXPERIENCE Ecosystem Package:
- Dynamic COM & universal service dispatch (:class:`DynamicCOMObject`, :class:`DynamicCOMService`)
- Universal rich-client controller & workbench catalog (:class:`UniversalClientController`, :class:`Workbenches`)
- Installation, CATEnv, and process discovery (:func:`discover_3dx_installations`, :func:`discover_ecosystem_summary`)
- Headless CLI & batch utilities (:class:`CATBatchRunner`)
- Cloud & On-Premise REST API client (:class:`ThreeDXPlatformClient`, :class:`EnoviaClient`)
- Brand controllers (:class:`DelmiaController`, :class:`BioviaRunner`, :class:`GeoviaRunner`, :class:`ExciteController`, :class:`SolidWorksController`)
"""
from __future__ import annotations

from pycatia3dx.ecosystem.brands import (
    BioviaRunner,
    DelmiaController,
    ExciteController,
    GeoviaRunner,
    SolidWorksController,
)
from pycatia3dx.ecosystem.catia_batch import BatchExecutionResult, CATBatchRunner
from pycatia3dx.ecosystem.discovery import (
    ThreeDXInstallation,
    discover_3dx_installations,
    discover_ecosystem_summary,
)
from pycatia3dx.ecosystem.dynamic_com import (
    DynamicCOMObject,
    DynamicCOMService,
    snake_to_com_candidates,
    unwrap_com_arg,
    wrap_com_result,
)
from pycatia3dx.ecosystem.platform_api import (
    EnoviaClient,
    PlatformAPIError,
    ThreeDXPlatformClient,
)
from pycatia3dx.ecosystem.universal_client import UniversalClientController, Workbenches

__all__ = [
    "BatchExecutionResult",
    "BioviaRunner",
    "CATBatchRunner",
    "DelmiaController",
    "DynamicCOMObject",
    "DynamicCOMService",
    "EnoviaClient",
    "ExciteController",
    "GeoviaRunner",
    "PlatformAPIError",
    "SolidWorksController",
    "ThreeDXInstallation",
    "ThreeDXPlatformClient",
    "UniversalClientController",
    "Workbenches",
    "discover_3dx_installations",
    "discover_ecosystem_summary",
    "snake_to_com_candidates",
    "unwrap_com_arg",
    "wrap_com_result",
]
