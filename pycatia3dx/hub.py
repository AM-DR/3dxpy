"""
Unified ``ThreeDExperience`` Hub — Single Entry Point for Every Tool in 3DEXPERIENCE.

Connects:
- **CATIA & Universal Rich-Client COM** (``dx.catia``, ``dx.client``)
- **SIMULIA Full Portfolio** (``dx.simulia``: ``abaqus``, ``inp``, ``odb``, ``isight``,
  ``tosca``, ``fesafe``, ``simpack``, ``cst``, ``powerflow``, ``xflow``, ``wave6``, ``client``)
- **DELMIA** Manufacturing & Robotics (``dx.delmia``)
- **ENOVIA / 3DSpace / 3DPassport / 3DSearch / 3DSwym** REST APIs (``dx.platform(...)``)
- **CATIA / 3DEXPERIENCE Batch & CATEnv CLI** (``dx.batch``)
- **BIOVIA**, **GEOVIA**, **3DEXCITE**, and **SOLIDWORKS** (``dx.biovia``, ``dx.geovia``,
  ``dx.excite``, ``dx.solidworks``)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pycatia3dx.ecosystem.brands import (
    BioviaRunner,
    DelmiaController,
    ExciteController,
    GeoviaRunner,
    SolidWorksController,
)
from pycatia3dx.ecosystem.catia_batch import CATBatchRunner
from pycatia3dx.ecosystem.discovery import discover_3dx_installations, discover_ecosystem_summary
from pycatia3dx.ecosystem.platform_api import ThreeDXPlatformClient
from pycatia3dx.ecosystem.universal_client import UniversalClientController, Workbenches
from pycatia3dx.simulia import SimuliaSuite

if TYPE_CHECKING:
    from pycatia3dx.interfaces.application import Application


class ThreeDExperience:
    """
    Unified Python facade to control all tools across the 3DEXPERIENCE platform.

    Instantiation is lightweight and never requires ``3DEXPERIENCE.exe`` to be
    running until rich-client COM properties (``dx.catia``, ``dx.client``, etc.)
    are accessed — allowing standalone SIMULIA solvers, Abaqus scripting, batch
    translators, and 3DSpace REST calls to work anywhere.

    Example::

        from pycatia3dx import ThreeDExperience

        dx = ThreeDExperience()

        # 1. Standalone Abaqus .inp + solver + CAE Python
        deck = dx.simulia.create_inp_deck("Demo")
        # ...
        abq_job = dx.simulia.abaqus.run_job("demo_job", "demo.inp", cpus=4)

        # 2. Rich-client CATIA / DELMIA / SIMULIA (when 3DEXPERIENCE.exe is open)
        app = dx.catia
        dx.client.switch_workbench(dx.workbenches.PART_DESIGN)

        # 3. Cloud / On-Premise 3DSpace (ENOVIA) REST API
        plm = dx.platform("https://my-tenant-space.3dexperience.3ds.com/enovia")
    """

    workbenches = Workbenches

    def __init__(self, application: Application | None = None):
        self._app = application
        self.simulia = SimuliaSuite(application=application)
        self.batch = CATBatchRunner()
        self.biovia = BioviaRunner()
        self.geovia = GeoviaRunner()
        self.excite = ExciteController()
        self.solidworks = SolidWorksController()
        self._client: UniversalClientController | None = None
        self._delmia: DelmiaController | None = None

    @property
    def catia(self) -> Application:
        """Connect to the running 3DEXPERIENCE rich client and return :class:`Application`."""
        if self._app is None:
            from pycatia3dx import catia3dx

            self._app = catia3dx()
            self.simulia.client._app = self._app
        return self._app

    @property
    def client(self) -> UniversalClientController:
        """Return the universal rich-client controller (workbenches, macros, PLM, dynamic COM)."""
        if self._client is None:
            self._client = UniversalClientController(application=self._app)
        elif self._app is not None and self._client._app is None:
            self._client._app = self._app
        return self._client

    @property
    def delmia(self) -> DelmiaController:
        """Return the DELMIA Robotics OLP, Machining, & Fitting controller."""
        if self._delmia is None:
            self._delmia = DelmiaController(application=self._app)
        elif self._app is not None and self._delmia._app is None:
            self._delmia._app = self._app
        return self._delmia

    def platform(
        self,
        space_url: str,
        *,
        passport_url: str | None = None,
        search_url: str | None = None,
        swym_url: str | None = None,
        security_context: str | None = None,
        tenant: str | None = None,
        verify_ssl: bool = True,
    ) -> ThreeDXPlatformClient:
        """Create a 3DEXPERIENCE Web/REST API client (ENOVIA / 3DSpace / 3DPassport / 3DSearch / 3DSwym)."""
        return ThreeDXPlatformClient(
            space_url=space_url,
            passport_url=passport_url,
            search_url=search_url,
            swym_url=swym_url,
            security_context=security_context,
            tenant=tenant,
            verify_ssl=verify_ssl,
        )

    enovia = platform

    @staticmethod
    def discover() -> dict[str, Any]:
        """Discover all local 3DEXPERIENCE installations, ``CATEnv`` files, and solver binaries."""
        return discover_ecosystem_summary()

    @staticmethod
    def installations():
        """Return structured :class:`ThreeDXInstallation` records found on this machine."""
        return discover_3dx_installations()
