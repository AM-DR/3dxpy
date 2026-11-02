"""
Universal 3DEXPERIENCE Rich-Client Controller.

Provides:
- :class:`Workbenches`: App / Workbench IDs across CATIA, SIMULIA, DELMIA,
  ENOVIA, BIOVIA, GEOVIA, and 3DEXCITE.
- :class:`UniversalClientController`: High-level Python driver to switch apps,
  launch commands, evaluate inline VBScript/CATScript/CATVBA macros, query/open/create/save
  PLM entities, and access *any* session service, editor service, or active feature
  dynamically via :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMObject`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from pycatia3dx import CATScriptLanguage, CatScriptLibraryType
from pycatia3dx.ecosystem.dynamic_com import DynamicCOMObject, unwrap_com_arg, wrap_com_result

if TYPE_CHECKING:
    from pycatia3dx.interfaces.application import Application
    from pycatia3dx.interfaces.editor import Editor
    from pycatia3dx.interfaces.service import Service


class Workbenches:
    """Common 3DEXPERIENCE App / Workbench identifiers across Dassault Systèmes brands."""

    # CATIA Design & Engineering
    PART_DESIGN = "PrtCfg"
    GENERATIVE_SHAPE_DESIGN = "PKT"
    WIREFRAME_AND_SURFACE = "WksCfg"
    SKETCHER = "CS0Wks"
    ASSEMBLY_DESIGN = "Assembly"
    DRAFTING = "Drw"
    SHEETMETAL_DESIGN = "SmdNewDesignWorkbench"
    COMPOSITES_DESIGN = "CpdConfiguration"
    STRUCTURE_DESIGN = "StrStructureDesignWorkbench"
    ELECTRICAL_3D_DESIGN = "Elec3DConductor"
    PCB_DESIGN = "PCBWorkbench"
    KNOWLEDGE_ADVISOR = "KweWorkbench"
    MECHANICAL_SYSTEMS_DESIGN = "KinematicsWorkbench"
    NATURAL_SKETCH = "CATNaturalSketchWkb"
    IMA_SUBDIVISION = "CATImaWorkbench"

    # SIMULIA In-Client Apps
    SIM_MECHANICAL_SCENARIO = "SimMechanicalScenarioCreation"
    SIM_STRUCTURAL_SCENARIO = "SimStructuralScenarioCreation"
    SIM_LINEAR_STRUCTURAL_SCENARIO = "SimLinearStructuralScenarioCreation"
    SIM_LINEAR_STRUCTURAL_VALIDATION = "SimLinearStructuralValidation"
    SIM_FEM_MODEL = "FmtModelAssembly"
    SIM_PHYSICS_RESULTS = "SimResultsWorkbench"

    # DELMIA Manufacturing, Robotics, & Ergonomics
    DELMIA_ROBOTICS_OLP = "DNBIgpOlpUseWkbench"
    DELMIA_ROBOT_TASK = "DELRobotSimulationWkb"
    DELMIA_ARC_WELDING = "DNBIgpArcWeldingUseWkbench"
    DELMIA_SPOT_WELDING = "DELSpotWeldingWkb"
    DELMIA_FITTING = "DNBFittingWorkbench"
    DELMIA_PRISMATIC_MACHINING = "PmgWorkbench"
    DELMIA_SURFACE_MACHINING = "SmgWorkbench"
    DELMIA_ERGONOMICS = "HumanBuilder"

    # ENOVIA / Digital Mockup / Review
    DMU_SECTIONING = "OpnsSectionWkb"
    DMU_INTERFERENCE = "InterferenceCheckWkb"
    PLM_VALIDATION = "VALValidationWkb"


class UniversalClientController:
    """
    Universal controller for the 3DEXPERIENCE rich client, enabling Python automation
    across CATIA, SIMULIA, DELMIA, ENOVIA, BIOVIA, GEOVIA, and 3DEXCITE apps.
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
    def active_editor(self) -> Editor:
        return self.application.active_editor

    def active_object(self) -> DynamicCOMObject:
        """Return the active PLM/CAD/Simulation/Manufacturing object as a ``DynamicCOMObject``."""
        return DynamicCOMObject(self.application.active_editor.active_com_object)

    def current_workbench(self) -> str:
        """Return the active 3DEXPERIENCE app / workbench identifier."""
        return self.application.get_workbench_id()

    def switch_workbench(self, workbench_id: str) -> None:
        """Activate any 3DEXPERIENCE app/workbench by ID (see :class:`Workbenches`)."""
        self.application.start_workbench(workbench_id)

    def run_command(self, command_id: str) -> None:
        """Trigger a one-shot 3DEXPERIENCE command header by ID or localized title."""
        self.application.start_command(command_id)

    def session_service(self, service_id: str) -> Service:
        """
        Retrieve *any* session-level service (typed wrapper if known, or
        :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMService` automatically).
        """
        return self.application.get_session_service(service_id)

    def editor_service(self, service_id: str, *, editor: Editor | None = None) -> Service:
        """
        Retrieve *any* editor-level service (typed wrapper if known, or
        :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMService` automatically).
        """
        target_editor = editor or self.application.active_editor
        return target_editor.get_service(service_id)

    # ------------------------------------------------------------------
    # Inline VBScript / CATScript / Macro Execution
    # ------------------------------------------------------------------
    def evaluate_vbscript(
        self,
        function_code: str,
        function_name: str,
        params: Sequence[Any] = (),
    ) -> Any:
        """Evaluate a VBScript ``Function`` inside the 3DEXPERIENCE scripting engine."""
        unwrapped = [unwrap_com_arg(p) for p in params]
        res = self.application.system_service.evaluate(
            function_code,
            CATScriptLanguage.CATVBScriptLanguage,
            function_name,
            unwrapped,
        )
        return wrap_com_result(res)

    def evaluate_catscript(
        self,
        function_code: str,
        function_name: str,
        params: Sequence[Any] = (),
    ) -> Any:
        """Evaluate a CATScript procedure/function inside 3DEXPERIENCE."""
        unwrapped = [unwrap_com_arg(p) for p in params]
        res = self.application.system_service.evaluate(
            function_code,
            CATScriptLanguage.CATBasicScriptLanguage,
            function_name,
            unwrapped,
        )
        return wrap_com_result(res)

    def run_inline_vbscript(self, statements: str, *args: Any) -> Any:
        """
        Execute arbitrary VBScript statements inside 3DEXPERIENCE without boilerplate.

        Inside ``statements``:
        - ``CATIA`` is available globally.
        - Arguments passed via ``*args`` are bound as ``arg0``, ``arg1``, ...
        - Assign ``RESULT = ...`` (or ``Set RESULT = ...``) to return a value to Python.
        """
        arg_names = [f"arg{i}" for i in range(len(args))]
        sig = ", ".join(arg_names)
        indented = "\n".join(f"    {ln}" for ln in statements.splitlines())
        vb_code = (
            f"Function _pycatia_inline({sig})\n"
            f"    Dim RESULT\n"
            f"    RESULT = Empty\n"
            f"{indented}\n"
            f"    If IsObject(RESULT) Then\n"
            f"        Set _pycatia_inline = RESULT\n"
            f"    Else\n"
            f"        _pycatia_inline = RESULT\n"
            f"    End If\n"
            f"End Function"
        )
        return self.evaluate_vbscript(vb_code, "_pycatia_inline", args)

    def run_macro_file(
        self,
        library_name: str,
        program_name: str,
        function_name: str = "CATMain",
        params: Sequence[Any] = (),
        *,
        library_type: int = CatScriptLibraryType.catScriptLibraryTypeDirectory,
    ) -> Any:
        """Execute an external ``.catvbs``, ``.CATScript``, or ``.catvba`` macro."""
        unwrapped = [unwrap_com_arg(p) for p in params]
        res = self.application.system_service.execute_script(
            library_name,
            library_type,
            program_name,
            function_name,
            unwrapped,
        )
        return wrap_com_result(res)

    # ------------------------------------------------------------------
    # High-level PLM Session Helpers (Search / Open / Create / Save / Refresh)
    # ------------------------------------------------------------------
    def search_plm(
        self,
        *,
        base_type: str | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> list[DynamicCOMObject]:
        """Search PLM database inside the rich client via ``Search`` session service."""
        from pycatia3dx.plm_access.search_service import SearchService

        svc = self.session_service("Search")
        search_svc = svc if isinstance(svc, SearchService) else SearchService(svc.com_object)
        db_search = search_svc.database_search
        if base_type:
            db_search.base_type = base_type
        if attributes:
            for attr_id, attr_val in attributes.items():
                db_search.add_easy_criteria(attr_id, attr_val)
        search_svc.search()
        entities = db_search.results
        return [DynamicCOMObject(entities.item(i).com_object) for i in range(1, entities.count + 1)]

    def open_plm_object(self, plm_entity: Any) -> Editor:
        """Open a searched ``PLMEntity`` into an authoring ``Editor`` via ``PLMOpenService``."""
        from pycatia3dx.interfaces.editor import Editor

        open_svc = self.session_service("PLMOpenService")
        vb_code = (
            "Function _pycatia_plm_open(openSvc, entity)\n"
            "    Dim edt\n"
            "    openSvc.PLMOpen entity, edt\n"
            "    Set _pycatia_plm_open = edt\n"
            "End Function"
        )
        edt = self.evaluate_vbscript(vb_code, "_pycatia_plm_open", [open_svc, plm_entity])
        if edt is None:
            raise RuntimeError("PLMOpenService.PLMOpen did not return an Editor.")
        return Editor(unwrap_com_arg(edt))

    def create_plm_entity(self, plm_type: str) -> Editor:
        """Create a new PLM authoring object (e.g. ``'3DShape'``, ``'VPMReference'``, ``'Drawing'``)."""
        from pycatia3dx.interfaces.editor import Editor

        new_svc = self.session_service("PLMNewService")
        vb_code = (
            "Function _pycatia_plm_new(newSvc, plmType)\n"
            "    Dim edt\n"
            "    newSvc.PLMCreate plmType, edt\n"
            "    Set _pycatia_plm_new = edt\n"
            "End Function"
        )
        edt = self.evaluate_vbscript(vb_code, "_pycatia_plm_new", [new_svc, plm_type])
        if edt is None:
            raise RuntimeError(f"PLMNewService.PLMCreate({plm_type!r}) did not return an Editor.")
        return Editor(unwrap_com_arg(edt))

    def save_session(self) -> None:
        """Propagate / save modified PLM objects in the session to 3DSpace."""
        prop_svc = self.session_service("PLMPropagateService")
        prop_svc.com_object.Save()

    def refresh_session(self) -> None:
        """Refresh open PLM objects from 3DSpace."""
        ref_svc = self.session_service("PLMRefreshService")
        DynamicCOMObject(ref_svc.com_object).perform_refresh()
