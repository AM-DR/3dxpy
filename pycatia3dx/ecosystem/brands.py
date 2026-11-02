"""
Dedicated Controllers for the Remaining Dassault Systèmes 3DEXPERIENCE Brands:
- **DELMIA** (:class:`DelmiaController` — Robotics OLP, Machining, Fitting, Ergonomics)
- **BIOVIA** (:class:`BioviaRunner` — Pipeline Pilot & Materials Studio)
- **GEOVIA** (:class:`GeoviaRunner` — Surpac, MineSched, Whittle)
- **3DEXCITE** (:class:`ExciteController` — DeltaGen scene/batch automation)
- **SOLIDWORKS** (:class:`SolidWorksController` — ``SldWorks.Application`` COM automation)
"""
from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from pycatia3dx import CATScriptLanguage
from pycatia3dx.dnb_fitting.fitting_service import FittingService
from pycatia3dx.dnb_igp_olp_use.calib_least_squares_service import CalibLeastSquaresService
from pycatia3dx.dnb_igp_olp_use.olp_download_service import OLPDownloadService
from pycatia3dx.dnb_igp_olp_use.olp_translator_helper import OLPTranslatorHelper
from pycatia3dx.dnb_igp_olp_use.olp_upload_service import OLPUploadService
from pycatia3dx.ecosystem.dynamic_com import DynamicCOMObject, unwrap_com_arg
from pycatia3dx.simulia.solvers import SolverProcessResult, _discover_tool_binary, _exec_tool

if TYPE_CHECKING:
    from pycatia3dx.interfaces.application import Application


# ======================================================================
# 1. DELMIA (Robotics, Offline Programming, Machining, Fitting, Ergonomics)
# ======================================================================
class DelmiaController:
    """
    High-level Python controller for **DELMIA** manufacturing, robotics offline
    programming (FANUC, KUKA, ABB, Motoman/Yaskawa, Universal Robots), fitting,
    and machining inside 3DEXPERIENCE.
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
    def olp_download_service(self) -> OLPDownloadService:
        svc = self.application.get_session_service("OlpDownloadService")
        return svc if isinstance(svc, OLPDownloadService) else OLPDownloadService(svc.com_object)

    @property
    def olp_upload_service(self) -> OLPUploadService:
        svc = self.application.get_session_service("OlpUploadService")
        return svc if isinstance(svc, OLPUploadService) else OLPUploadService(svc.com_object)

    @property
    def olp_translator_helper(self) -> OLPTranslatorHelper:
        svc = self.application.get_session_service("OlpTranslatorHelper")
        return svc if isinstance(svc, OLPTranslatorHelper) else OLPTranslatorHelper(svc.com_object)

    @property
    def calibration_service(self) -> CalibLeastSquaresService:
        svc = self.application.get_session_service("CalibLeastSquaresService")
        return svc if isinstance(svc, CalibLeastSquaresService) else CalibLeastSquaresService(svc.com_object)

    def fitting_service(self) -> FittingService:
        svc = self.application.active_editor.get_service("FittingService")
        return svc if isinstance(svc, FittingService) else FittingService(svc.com_object)

    def download_robot_programs(
        self,
        robot_occurrence: Any,
        tasks: Sequence[Any],
        output_dir: str | pathlib.Path,
        *,
        translator: str = "",
        download_call_tasks: bool = True,
    ) -> pathlib.Path:
        """
        Translate DELMIA robot tasks into native controller programs (TP/LS, KRL,
        RAPID, INFORM) and save them to ``output_dir``.
        """
        out_folder = pathlib.Path(output_dir).resolve()
        out_folder.mkdir(parents=True, exist_ok=True)
        dl = self.olp_download_service
        dl.com_object.Resource = unwrap_com_arg(robot_occurrence)
        dl.download_call_tasks = download_call_tasks
        dl.translator = translator

        ubound = len(tasks) - 1
        if ubound < 0:
            raise ValueError("tasks must contain at least one DELMIA robot task.")

        task_args = [unwrap_com_arg(t) for t in tasks]
        arg_names = [f"t{i}" for i in range(len(task_args))]
        assigns = "\n".join(f"    Set arr({i}) = t{i}" for i in range(len(task_args)))
        sig = ", ".join(["dlSvc", *arg_names])
        vb_code = (
            f"Function _pycatia_olp_dl({sig})\n"
            f"    ReDim arr({ubound})\n"
            f"{assigns}\n"
            f"    dlSvc.Download arr\n"
            f"    _pycatia_olp_dl = True\n"
            f"End Function"
        )
        self.application.system_service.evaluate(
            vb_code,
            CATScriptLanguage.CATVBScriptLanguage,
            "_pycatia_olp_dl",
            [dl.com_object, *task_args],
        )
        dl.save_to_folder(str(out_folder))
        dl.finalize()
        return out_folder

    def upload_robot_programs(
        self,
        robot_occurrence: Any,
        program_files: Sequence[str | pathlib.Path],
        *,
        translator: str = "",
        replace_tasks: bool = True,
    ) -> None:
        """Upload native robot program files from disk into DELMIA 3DEXPERIENCE tasks."""
        if not program_files:
            raise ValueError("program_files must contain at least one robot program path.")

        up = self.olp_upload_service
        up.com_object.Resource = unwrap_com_arg(robot_occurrence)
        up.translator = translator
        up.replace_tasks = replace_tasks

        resolved_files = [str(pathlib.Path(p).resolve()) for p in program_files]
        ubound = len(resolved_files) - 1
        arg_names = [f"f{i}" for i in range(len(resolved_files))]
        assigns = "\n".join(f"    arr({i}) = f{i}" for i in range(len(resolved_files)))
        sig = ", ".join(["upSvc", *arg_names])
        vb_code = (
            f"Function _pycatia_olp_up({sig})\n"
            f"    ReDim arr({ubound})\n"
            f"{assigns}\n"
            f"    upSvc.Files = arr\n"
            f"    _pycatia_olp_up = True\n"
            f"End Function"
        )
        self.application.system_service.evaluate(
            vb_code,
            CATScriptLanguage.CATVBScriptLanguage,
            "_pycatia_olp_up",
            [up.com_object, *resolved_files],
        )
        up.parse()
        up.upload()
        up.post_process()
        up.finalize()


# ======================================================================
# 2. BIOVIA (Pipeline Pilot & Materials Studio)
# ======================================================================
class BioviaRunner:
    """
    Driver for **BIOVIA Pipeline Pilot** (``cstool`` CLI protocol execution)
    and **BIOVIA Materials Studio** (``RunMatScript`` Perl/MaterialsScript execution).
    """

    def __init__(
        self,
        pipeline_pilot_exe: str | pathlib.Path | None = None,
        materials_studio_exe: str | pathlib.Path | None = None,
    ):
        self._pp_explicit = pipeline_pilot_exe
        self._ms_explicit = materials_studio_exe

    @property
    def pipeline_pilot_executable(self) -> str:
        return (
            _discover_tool_binary(
                self._pp_explicit,
                ("PIPELINE_PILOT_CSTOOL", "BIOVIA_CSTOOL"),
                ("cstool",),
            )
            or "cstool"
        )

    @property
    def materials_studio_executable(self) -> str:
        return (
            _discover_tool_binary(
                self._ms_explicit,
                ("MATERIALS_STUDIO_CMD", "RUNMATSCRIPT_PATH"),
                ("RunMatScript", "MatServer"),
            )
            or "RunMatScript"
        )

    def run_pipeline_pilot_protocol(
        self,
        protocol_path: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        server: str | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute a BIOVIA Pipeline Pilot protocol via ``cstool``."""
        cmd = [self.pipeline_pilot_executable]
        if server:
            cmd.extend(["-server", server])
        cmd.extend(["-run", protocol_path])
        if parameters:
            for k, v in parameters.items():
                cmd.extend(["-param", f"{k}={v}"])
        return _exec_tool("BIOVIA Pipeline Pilot", cmd, cwd=cwd, timeout=timeout)

    def run_materials_script(
        self,
        perl_script: str | pathlib.Path,
        *,
        project_name: str | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute a BIOVIA Materials Studio ``.pl`` MaterialsScript."""
        script_p = pathlib.Path(perl_script).resolve()
        cmd = [self.materials_studio_executable]
        if project_name:
            cmd.append(project_name)
        cmd.append(str(script_p))
        return _exec_tool("BIOVIA Materials Studio", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 3. GEOVIA (Surpac, MineSched, Whittle)
# ======================================================================
class GeoviaRunner:
    """Driver for **GEOVIA Surpac** (``.mac`` / ``.tcl`` macro automation) & **MineSched**."""

    def __init__(self, surpac_exe: str | pathlib.Path | None = None):
        self._explicit = surpac_exe

    @property
    def surpac_executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("GEOVIA_SURPAC_CMD", "SURPAC_EXE"),
                ("surpac2", "surpac"),
            )
            or "surpac2"
        )

    def run_surpac_macro(
        self,
        macro_file: str | pathlib.Path,
        *,
        work_directory: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute a GEOVIA Surpac ``.mac`` (SCL) or ``.tcl`` geological/mining script."""
        cmd = [self.surpac_executable, "-macro", str(pathlib.Path(macro_file).resolve())]
        return _exec_tool("GEOVIA Surpac", cmd, cwd=work_directory, timeout=timeout)


# ======================================================================
# 4. 3DEXCITE (DeltaGen Visualization & Rendering)
# ======================================================================
class ExciteController:
    """Driver for **3DEXCITE DeltaGen** batch rendering & scene automation."""

    def __init__(self, deltagen_exe: str | pathlib.Path | None = None):
        self._explicit = deltagen_exe

    @property
    def executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("DELTAGEN_EXE", "EXCITE_CMD"),
                ("deltagen", "DeltaGen"),
            )
            or "deltagen"
        )

    def render_scene_batch(
        self,
        scene_file: str | pathlib.Path,
        *,
        script_file: str | pathlib.Path | None = None,
        headless: bool = True,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute a 3DEXCITE DeltaGen scene/render script."""
        cmd = [self.executable, str(pathlib.Path(scene_file).resolve())]
        if headless:
            cmd.append("-nogui")
        if script_file is not None:
            cmd.extend(["-script", str(pathlib.Path(script_file).resolve())])
        return _exec_tool("3DEXCITE DeltaGen", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 5. SOLIDWORKS / 3DEXPERIENCE SOLIDWORKS Connected (COM Bridge)
# ======================================================================
class SolidWorksController:
    """
    Windows COM controller for **SOLIDWORKS** and **3DEXPERIENCE SOLIDWORKS Connected**
    (``SldWorks.Application``), wrapped with :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMObject`.
    """

    DOC_PART = 1
    DOC_ASSEMBLY = 2
    DOC_DRAWING = 3

    def __init__(self, prog_id: str = "SldWorks.Application"):
        self.prog_id = prog_id
        self._sw: DynamicCOMObject | None = None

    def connect(self, *, visible: bool = True) -> DynamicCOMObject:
        """Connect to or launch SOLIDWORKS via COM."""
        try:
            from win32com.client import Dispatch
        except ImportError as exc:
            raise ImportError("pywin32 is required for SOLIDWORKS COM automation.") from exc

        self._sw = DynamicCOMObject(Dispatch(self.prog_id))
        try:
            self._sw.visible = visible
        except Exception:
            pass
        return self._sw

    @property
    def app(self) -> DynamicCOMObject:
        return self._sw if self._sw is not None else self.connect()

    def active_doc(self) -> DynamicCOMObject:
        """Return the currently active ``IModelDoc2`` wrapped as ``DynamicCOMObject``."""
        return self.app.active_doc

    def open_doc(
        self,
        file_path: str | pathlib.Path,
        *,
        doc_type: int | None = None,
        options: int = 1,
        configuration: str = "",
    ) -> DynamicCOMObject:
        """Open a ``.SLDPRT``, ``.SLDASM``, or ``.SLDDRW`` document."""
        p = pathlib.Path(file_path).resolve()
        if doc_type is None:
            ext = p.suffix.lower()
            if ext == ".sldasm":
                doc_type = self.DOC_ASSEMBLY
            elif ext == ".slddrw":
                doc_type = self.DOC_DRAWING
            else:
                doc_type = self.DOC_PART
        # OpenDoc6(FileName, Type, Options, Configuration, Errors, Warnings)
        res = self.app.call_com("OpenDoc6", str(p), doc_type, options, configuration, 0, 0)
        return res[0] if isinstance(res, tuple) else res

    def export_file(self, output_path: str | pathlib.Path, *, model_doc: DynamicCOMObject | None = None) -> bool:
        """Export the active SOLIDWORKS model to STEP, IGES, STL, Parasolid, or PDF."""
        doc = model_doc or self.active_doc()
        out = str(pathlib.Path(output_path).resolve())
        res = doc.extension.call_com("SaveAs3", out, 0, 1, None, None, 0, 0)
        return bool(res[0] if isinstance(res, tuple) else res)

    def run_macro(
        self,
        macro_path: str | pathlib.Path,
        module_name: str = "main",
        procedure_name: str = "main",
    ) -> bool:
        """Execute a SOLIDWORKS VBA ``.swp`` macro."""
        res = self.app.call_com(
            "RunMacro2",
            str(pathlib.Path(macro_path).resolve()),
            module_name,
            procedure_name,
            1,
            0,
        )
        return bool(res[0] if isinstance(res, tuple) else res)
