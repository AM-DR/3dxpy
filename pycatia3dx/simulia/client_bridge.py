"""
In-Client 3DEXPERIENCE SIMULIA Controller (``sma_*``, ``sim_*``, ``fmt_mode``)
and Bridge to Standalone Solvers.

Wraps the rich-client COM simulation services (:class:`SIMPLMService`,
:class:`SimInitializationService`, :class:`SimExecutionService`,
:class:`SimSimulationService`, :class:`SimRepServices`,
:class:`SimDynClashServices`) into a clean Python workflow API, handling COM
``[out]`` reference parameters via ``SystemService.Evaluate`` automatically.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pycatia3dx import CATScriptLanguage
from pycatia3dx.ecosystem.dynamic_com import DynamicCOMObject, unwrap_com_arg
from pycatia3dx.interfaces.editor import Editor
from pycatia3dx.plm_simulation_engine.sim_dyn_clash_services import SimDynClashServices
from pycatia3dx.sim_plm.sim_plm_service import SIMPLMService
from pycatia3dx.sim_plm.sim_simulation_service import SimSimulationService
from pycatia3dx.sim_plm.simulation_reference import SimulationReference
from pycatia3dx.sim_rep.sim_rep_services import SimRepServices
from pycatia3dx.sma_mpa_foundation.sim_execution_service import SimExecutionService
from pycatia3dx.sma_mpa_foundation.sim_initialization_service import SimInitializationService

if TYPE_CHECKING:
    from pycatia3dx.interfaces.application import Application


class SimulationTypes:
    """Standard 3DEXPERIENCE ``SimPLMService.PLMCreate`` simulation types."""

    MULTIPHYSICS_FEA = "SMAFeaPLMNewSimu"
    MANUFACTURING = "DELPLMSimulation"
    PRODUCTION = "DELPSSSimulation"
    KINEMATICS = "CATKinPLMNew"
    LOGICAL = "LogicalSimulation"


class ScenarioApps:
    """Standard 3DEXPERIENCE simulation scenario app identifiers."""

    MECHANICAL_SCENARIO = "SimMechanicalScenarioCreation"
    STRUCTURAL_SCENARIO = "SimStructuralScenarioCreation"
    LINEAR_STRUCTURAL_SCENARIO = "SimLinearStructuralScenarioCreation"
    LINEAR_STRUCTURAL_VALIDATION = "SimLinearStructuralValidation"


class PhysicsDomains:
    """Standard ``SimInitializationService`` physics domain identifiers."""

    GENERAL = "SimGeneral"
    STRUCTURAL = "SimStructural"
    THERMAL = "SimThermal"
    THERMAL_STRUCTURAL = "SimThermalStructural"


class SimuliaClientController:
    """
    High-level orchestrator for simulation exposed inside the 3DEXPERIENCE rich
    client (``sma_*``, ``sim_plm``, ``sim_rep``, ``fmt_mode``).
    """

    def __init__(self, application: Application | None = None):
        self._app = application

    @property
    def application(self) -> Application:
        if self._app is None:
            from pycatia3dx import catia3dx

            self._app = catia3dx()
        return self._app

    @property
    def plm_service(self) -> SIMPLMService:
        svc = self.application.get_session_service("SimPLMService")
        return svc if isinstance(svc, SIMPLMService) else SIMPLMService(svc.com_object)

    @property
    def initialization_service(self) -> SimInitializationService:
        svc = self.application.get_session_service("SimInitializationService")
        return svc if isinstance(svc, SimInitializationService) else SimInitializationService(svc.com_object)

    @property
    def execution_service(self) -> SimExecutionService:
        svc = self.application.get_session_service("SimExecutionService")
        return svc if isinstance(svc, SimExecutionService) else SimExecutionService(svc.com_object)

    @property
    def simulation_service(self) -> SimSimulationService:
        svc = self.application.get_session_service("SimSimulationService")
        return svc if isinstance(svc, SimSimulationService) else SimSimulationService(svc.com_object)

    def get_rep_services(self, editor: Editor | None = None) -> SimRepServices:
        edt = editor or self.application.active_editor
        svc = edt.get_service("SimRepServices")
        return svc if isinstance(svc, SimRepServices) else SimRepServices(svc.com_object)

    def get_clash_services(self, editor: Editor | None = None) -> SimDynClashServices:
        edt = editor or self.application.active_editor
        svc = edt.get_service("SIMDynClashServices")
        return svc if isinstance(svc, SimDynClashServices) else SimDynClashServices(svc.com_object)

    def create_simulation(
        self,
        name: str,
        context_entity: Any,
        *,
        simulation_type: str = SimulationTypes.MULTIPHYSICS_FEA,
        scenario_app: str | None = ScenarioApps.MECHANICAL_SCENARIO,
        physics_domain: str | None = PhysicsDomains.STRUCTURAL,
    ) -> tuple[SimulationReference, Editor]:
        """
        Initialize and create a new 3DEXPERIENCE Simulation PLM object attached
        to ``context_entity`` (a ``PLMEntity`` / ``VPMReference``), returning
        ``(SimulationReference, Editor)``.
        """
        if simulation_type == SimulationTypes.MULTIPHYSICS_FEA and scenario_app and physics_domain:
            self.initialization_service.set_simulation_initialization(scenario_app, physics_domain)

        sim_svc = self.plm_service
        ctx_com = unwrap_com_arg(context_entity)

        vb_code = (
            "Function _pycatia_plm_create_sim(simSvc, simName, simType, ctx)\n"
            "    Dim oSim, oEdt\n"
            "    simSvc.PLMCreate simName, simType, ctx, oSim, oEdt\n"
            "    _pycatia_plm_create_sim = Array(oSim, oEdt)\n"
            "End Function"
        )
        res = self.application.system_service.evaluate(
            vb_code,
            CATScriptLanguage.CATVBScriptLanguage,
            "_pycatia_plm_create_sim",
            [sim_svc.com_object, name, simulation_type, ctx_com],
        )
        if not res or len(res) < 2 or res[0] is None:
            raise RuntimeError(
                f"SimPLMService.PLMCreate failed for name={name!r}, type={simulation_type!r}."
            )
        return SimulationReference(res[0]), Editor(res[1])

    def execute_all_cases(self, simulation_ref: SimulationReference | Any) -> bool:
        """Execute all analysis cases inside ``simulation_ref`` inside the 3DX client."""
        target = simulation_ref if hasattr(simulation_ref, "com_object") else DynamicCOMObject(simulation_ref)
        return bool(self.execution_service.basic_execute_all(target))

    def active_simulation_object(self) -> DynamicCOMObject:
        """Return the active simulation/FEM object in the current editor as a dynamic proxy."""
        return DynamicCOMObject(self.application.active_editor.active_com_object)
