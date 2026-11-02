"""
Unified SIMULIA Suite for ``pycatia3dx`` — covering both in-client 3DEXPERIENCE
simulation (``sma_*``, ``sim_*``, ``fmt_mode``) and standalone/embedded SIMULIA
solvers & Python scripting environments:

- **Abaqus** (:class:`AbaqusRunner`, :class:`AbaqusInpDeck`, :class:`AbaqusOdbReader`)
- **Isight / SEE** (:class:`IsightRunner`)
- **Tosca Structure & Fluid** (:class:`ToscaRunner`)
- **fe-safe** (:class:`FeSafeRunner`)
- **Simpack** (:class:`SimpackRunner`)
- **CST Studio Suite** (:class:`CSTController`)
- **PowerFLOW & XFlow** (:class:`PowerFlowRunner`, :class:`XFlowRunner`)
- **Wave6** (:class:`Wave6Runner`)
- **In-Client SIMULIA** (:class:`SimuliaClientController`)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pycatia3dx.simulia.abaqus import (
    AbaqusCommandResult,
    AbaqusIncrement,
    AbaqusJobStatus,
    AbaqusRunner,
    find_abaqus_executable,
    inspect_job_files,
    parse_dat_file,
    parse_msg_file,
    parse_sta_file,
)
from pycatia3dx.simulia.client_bridge import (
    PhysicsDomains,
    ScenarioApps,
    SimuliaClientController,
    SimulationTypes,
)
from pycatia3dx.simulia.inp_builder import AbaqusInpDeck, InpKeywordBlock
from pycatia3dx.simulia.odb_reader import AbaqusOdbReader
from pycatia3dx.simulia.solvers import (
    CSTController,
    FeSafeRunner,
    IsightRunner,
    PowerFlowRunner,
    SimpackRunner,
    SolverProcessResult,
    ToscaRunner,
    Wave6Runner,
    XFlowRunner,
)

if TYPE_CHECKING:
    from pycatia3dx.interfaces.application import Application


class SimuliaSuite:
    """
    Aggregated facade providing one-stop access to every SIMULIA solver and
    in-client simulation capability.
    """

    def __init__(self, application: Application | None = None):
        self._app = application
        self.abaqus = AbaqusRunner()
        self.isight = IsightRunner()
        self.tosca = ToscaRunner()
        self.fesafe = FeSafeRunner()
        self.simpack = SimpackRunner()
        self.cst = CSTController()
        self.powerflow = PowerFlowRunner()
        self.xflow = XFlowRunner()
        self.wave6 = Wave6Runner()
        self.client = SimuliaClientController(application=application)

    def create_inp_deck(self, heading: str | None = None) -> AbaqusInpDeck:
        """Create a new pure-Python Abaqus ``.inp`` finite-element model deck."""
        return AbaqusInpDeck(heading=heading)

    def load_inp_deck(self, path: str) -> AbaqusInpDeck:
        """Load an existing Abaqus ``.inp`` file from disk."""
        return AbaqusInpDeck.from_file(path)

    def open_odb(self, odb_path: str, *, read_only: bool = True) -> AbaqusOdbReader:
        """Open an Abaqus ``.odb`` output database via ``AbaqusOdbReader``."""
        return AbaqusOdbReader(odb_path, runner=self.abaqus, read_only=read_only)


__all__ = [
    "AbaqusCommandResult",
    "AbaqusIncrement",
    "AbaqusInpDeck",
    "AbaqusJobStatus",
    "AbaqusOdbReader",
    "AbaqusRunner",
    "CSTController",
    "FeSafeRunner",
    "InpKeywordBlock",
    "IsightRunner",
    "PhysicsDomains",
    "PowerFlowRunner",
    "ScenarioApps",
    "SimpackRunner",
    "SimuliaClientController",
    "SimuliaSuite",
    "SimulationTypes",
    "SolverProcessResult",
    "ToscaRunner",
    "Wave6Runner",
    "XFlowRunner",
    "find_abaqus_executable",
    "inspect_job_files",
    "parse_dat_file",
    "parse_msg_file",
    "parse_sta_file",
]
