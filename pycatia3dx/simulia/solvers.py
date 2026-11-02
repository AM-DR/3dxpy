"""
Drivers for the broader SIMULIA Solver Portfolio:
- **Isight / SIMULIA Execution Engine (SEE)** (:class:`IsightRunner`)
- **Tosca Structure & Tosca Fluid** (:class:`ToscaRunner`)
- **fe-safe** Fatigue Analysis (:class:`FeSafeRunner`)
- **Simpack** Multibody Simulation (:class:`SimpackRunner`)
- **CST Studio Suite** Electromagnetics (:class:`CSTController` — COM + CLI)
- **PowerFLOW** & **XFlow** CFD (:class:`PowerFlowRunner`, :class:`XFlowRunner`)
- **Wave6** Vibro-Acoustics (:class:`Wave6Runner`)
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass
class SolverProcessResult:
    """Standardized execution result for standalone SIMULIA solver invocations."""

    tool: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    cwd: pathlib.Path

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def _safe_exists(p: pathlib.Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


def _discover_tool_binary(
    explicit: str | pathlib.Path | None,
    env_vars: Sequence[str],
    binary_names: Sequence[str],
    extra_dirs: Sequence[pathlib.Path] = (),
) -> str | None:
    if explicit:
        p = pathlib.Path(explicit)
        if _safe_exists(p):
            return str(p)
        w = shutil.which(str(explicit))
        return w or str(explicit)

    for ev in env_vars:
        val = os.environ.get(ev)
        if val:
            if _safe_exists(pathlib.Path(val)):
                return val
            w = shutil.which(val)
            if w:
                return w

    for name in binary_names:
        w = shutil.which(name)
        if w:
            return w

    search_roots: list[pathlib.Path] = list(extra_dirs)
    if sys.platform == "win32":
        for drive in ("C:\\", "D:\\"):
            d = pathlib.Path(drive)
            search_roots.extend([
                d / "SIMULIA" / "Commands",
                d / "SIMULIA",
                d / "Program Files" / "Dassault Systemes",
                d / "Program Files (x86)" / "CST Studio Suite 2026",
                d / "Program Files (x86)" / "CST Studio Suite 2025",
                d / "Program Files (x86)" / "CST Studio Suite 2024",
                d / "Program Files" / "CST Studio Suite 2026",
                d / "Program Files" / "CST Studio Suite 2025",
                d / "Program Files" / "CST Studio Suite 2024",
            ])
    else:
        search_roots.extend([
            pathlib.Path("/opt/SIMULIA/Commands"),
            pathlib.Path("/var/DassaultSystemes/SIMULIA/Commands"),
            pathlib.Path("/opt/cst/CST_STUDIO_SUITE_2025"),
            pathlib.Path("/opt/cst/CST_STUDIO_SUITE_2024"),
        ])

    exts = (".bat", ".cmd", ".exe", "") if sys.platform == "win32" else ("",)
    for root in search_roots:
        if not _safe_exists(root):
            continue
        for name in binary_names:
            for ext in exts:
                cand = root / f"{name}{ext}"
                if _safe_exists(cand):
                    return str(cand)
                amd_cand = root / "AMD64" / f"{name}{ext}"
                if _safe_exists(amd_cand):
                    return str(amd_cand)
    return None


def _exec_tool(
    tool_name: str,
    cmd: list[str],
    *,
    cwd: str | pathlib.Path | None = None,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
) -> SolverProcessResult:
    work_dir = pathlib.Path(cwd).resolve() if cwd else pathlib.Path.cwd()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(work_dir),
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{tool_name} executable {cmd[0]!r} was not found on PATH or standard SIMULIA directories."
        ) from exc

    return SolverProcessResult(
        tool=tool_name,
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        cwd=work_dir,
    )


# ======================================================================
# 1. SIMULIA Isight & SIMULIA Execution Engine (SEE)
# ======================================================================
class IsightRunner:
    """
    Driver for **SIMULIA Isight** and **SIMULIA Execution Engine (SEE)** via ``fipercmd``.

    Executes ``.zmf`` process-integration / design-of-experiments / multidisciplinary
    optimization workflows locally or on a remote SEE server.
    """

    def __init__(self, executable: str | pathlib.Path | None = None):
        self._explicit = executable

    @property
    def executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("ISIGHT_CMD", "FIPERCMD_PATH"),
                ("fipercmd", "isight"),
            )
            or "fipercmd"
        )

    def build_run_command(
        self,
        zmf_model: str | pathlib.Path,
        *,
        parameters: Mapping[str, Any] | None = None,
        result_file: str | pathlib.Path | None = None,
        see_profile: str | None = None,
        log_level: str = "info",
    ) -> list[str]:
        parts = [f"start model:{zmf_model}"]
        if parameters:
            param_pairs = ";".join(f"{k}={v}" for k, v in parameters.items())
            parts.append(f'parm:"{param_pairs}"')
        if result_file:
            parts.append(f"file:{result_file}")
        parts.append("wait:yes")

        cmd = [self.executable]
        if see_profile:
            cmd.extend(["-profile", see_profile])
        cmd.extend(["-log", log_level, " ".join(parts)])
        return cmd

    def run_workflow(
        self,
        zmf_model: str | pathlib.Path,
        *,
        parameters: Mapping[str, Any] | None = None,
        result_file: str | pathlib.Path | None = None,
        see_profile: str | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute an Isight ``.zmf`` workflow and wait for completion."""
        cmd = self.build_run_command(
            zmf_model,
            parameters=parameters,
            result_file=result_file,
            see_profile=see_profile,
        )
        return _exec_tool("SIMULIA Isight", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 2. SIMULIA Tosca Structure & Tosca Fluid
# ======================================================================
class ToscaRunner:
    """
    Driver for **SIMULIA Tosca Structure** (topology, shape, bead, sizing optimization)
    and **Tosca Fluid**.
    """

    def __init__(self, executable: str | pathlib.Path | None = None):
        self._explicit = executable

    @property
    def executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("TOSCA_CMD", "TOSCA_PATH"),
                ("tosca", "tosca_driver"),
            )
            or "tosca"
        )

    @staticmethod
    def build_topology_par(
        *,
        fem_input: str | pathlib.Path,
        design_elset: str = "ALL_ELEMENTS",
        volume_fraction: float = 0.3,
        max_iterations: int = 50,
        frozen_nset: str | None = None,
    ) -> str:
        """Generate a ready-to-run Tosca Structure ``.par`` topology optimization deck."""
        lines = [
            "! Generated by pycatia3dx.simulia.ToscaRunner",
            "FEM_INPUT",
            "  ID_NAME = FE_MODEL",
            f"  FILE = {pathlib.Path(fem_input).name}",
            "END_",
            "",
            "DV_TOPO",
            "  ID_NAME = DESIGN_AREA",
            f"  EL_GROUP = {design_elset}",
            "END_",
        ]
        if frozen_nset:
            lines.extend([
                "",
                "DVCON_TOPO",
                "  ID_NAME = FROZEN_BC",
                "  EL_GROUP = ALL_ELEMENTS",
                "  CHECK_TYPE = FROZEN",
                f"  ND_GROUP = {frozen_nset}",
                "END_",
            ])
        lines.extend([
            "",
            "DRESP",
            "  ID_NAME = DRESP_STIFFNESS",
            "  DEF_TYPE = SYSTEM",
            "  TYPE = STRAIN_ENERGY",
            "  EL_GROUP = ALL_ELEMENTS",
            "END_",
            "",
            "DRESP",
            "  ID_NAME = DRESP_VOL",
            "  DEF_TYPE = SYSTEM",
            "  TYPE = VOLUME",
            f"  EL_GROUP = {design_elset}",
            "END_",
            "",
            "OBJ_FUNC",
            "  ID_NAME = MIN_COMPLIANCE",
            "  DRESP = DRESP_STIFFNESS",
            "  TARGET = MIN",
            "END_",
            "",
            "CONSTRAINT",
            "  ID_NAME = VOL_CONSTRAINT",
            "  DRESP = DRESP_VOL",
            "  MAGNITUDE = REL",
            f"  LE_VALUE = {volume_fraction}",
            "END_",
            "",
            "OPTIMIZE",
            "  ID_NAME = TOPO_OPT",
            "  DV = DESIGN_AREA",
            "  OBJ_FUNC = MIN_COMPLIANCE",
            "  CONSTRAINT = VOL_CONSTRAINT",
            *(["  DVCON = FROZEN_BC"] if frozen_nset else []),
            "  STRATEGY = TOPO_SENSITIVITY",
            "END_",
            "",
            "STOP",
            "  ID_NAME = GLOBAL_STOP",
            f"  ITER_MAX = {int(max_iterations)}",
            "END_",
            "",
            "EXIT",
            "",
        ])
        return "\n".join(lines)

    def build_command(
        self,
        par_file: str | pathlib.Path,
        *,
        job_name: str | None = None,
        solver: str = "abaqus",
        cpus: int | None = None,
        loglevel: str = "INFO",
    ) -> list[str]:
        cmd = [self.executable, "optimize", "-p", str(par_file), "-s", solver, "--loglevel", loglevel]
        if job_name:
            cmd.extend(["-j", job_name])
        if cpus is not None:
            cmd.extend(["-scpus", str(int(cpus))])
        return cmd

    def run_optimization(
        self,
        par_file: str | pathlib.Path,
        *,
        job_name: str | None = None,
        solver: str = "abaqus",
        cpus: int | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Run a Tosca optimization job."""
        cmd = self.build_command(par_file, job_name=job_name, solver=solver, cpus=cpus)
        return _exec_tool("SIMULIA Tosca", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 3. SIMULIA fe-safe (Fatigue & Durability)
# ======================================================================
class FeSafeRunner:
    """Driver for **SIMULIA fe-safe** multiaxial fatigue analysis."""

    def __init__(self, executable: str | pathlib.Path | None = None):
        self._explicit = executable

    @property
    def executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("FESAFE_CMD", "FESAFE_PATH"),
                ("fe-safe", "fe-safe_cl", "fesafe"),
            )
            or "fe-safe"
        )

    @staticmethod
    def build_fatigue_macro(
        *,
        input_odb: str | pathlib.Path,
        output_odb: str | pathlib.Path,
        material_name: str = "SAE-1045",
        stress_units: str = "MPa",
        scale_factor: float = 1.0,
    ) -> str:
        """Build a headless fe-safe batch ``.macro`` script."""
        return "\n".join([
            f"# Generated by pycatia3dx.simulia.FeSafeRunner",
            f"open_fem_file={pathlib.Path(input_odb).resolve()}",
            f"stress_units={stress_units}",
            f"default_material={material_name}",
            f"loading_scale={scale_factor}",
            f"output_file={pathlib.Path(output_odb).resolve()}",
            "analyse",
            "exit",
            "",
        ])

    def run_macro(
        self,
        macro_file: str | pathlib.Path,
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Run an fe-safe ``.macro`` durability analysis job in batch mode."""
        cmd = [self.executable, f"macro={macro_file}", "batch=true"]
        return _exec_tool("SIMULIA fe-safe", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 4. SIMULIA Simpack (Multibody Dynamics)
# ======================================================================
class SimpackRunner:
    """Driver for **SIMULIA Simpack** multibody simulation (``simpack-slv`` & ``simpack-script``)."""

    def __init__(
        self,
        solver_exe: str | pathlib.Path | None = None,
        script_exe: str | pathlib.Path | None = None,
    ):
        self._solver_explicit = solver_exe
        self._script_explicit = script_exe

    @property
    def solver_executable(self) -> str:
        return (
            _discover_tool_binary(
                self._solver_explicit,
                ("SIMPACK_SLV",),
                ("simpack-slv",),
            )
            or "simpack-slv"
        )

    @property
    def script_executable(self) -> str:
        return (
            _discover_tool_binary(
                self._script_explicit,
                ("SIMPACK_SCRIPT",),
                ("simpack-script",),
            )
            or "simpack-script"
        )

    def run_time_integration(
        self,
        spck_model: str | pathlib.Path,
        *,
        cpus: int | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute Simpack time-domain integration on ``.spck``."""
        cmd = [self.solver_executable, "--time-integration", str(spck_model)]
        if cpus is not None:
            cmd.extend(["--parallel", str(int(cpus))])
        return _exec_tool("SIMULIA Simpack", cmd, cwd=cwd, timeout=timeout)

    def run_eigensolution(
        self,
        spck_model: str | pathlib.Path,
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Compute linearized eigenmodes of a ``.spck`` model."""
        cmd = [self.solver_executable, "--eigenvalues", str(spck_model)]
        return _exec_tool("SIMULIA Simpack", cmd, cwd=cwd, timeout=timeout)

    def run_qs_script(
        self,
        script_file: str | pathlib.Path,
        args: Sequence[str] = (),
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute a Simpack ``.sjs`` scripting file."""
        cmd = [self.script_executable, str(script_file), *(str(a) for a in args)]
        return _exec_tool("SIMULIA Simpack Script", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 5. SIMULIA CST Studio Suite (Electromagnetics — COM + CLI)
# ======================================================================
class CSTController:
    """
    Dual-mode driver for **SIMULIA CST Studio Suite** (Microwave, EM, Particle, Thermal):
    - **Windows COM mode**: Connects to ``CSTStudio.Application`` wrapped as a
      :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMObject` for interactive
      parameter updates, geometry modeling, VBA macro execution, and solver launches.
    - **Headless CLI mode**: Invokes ``cst_design_environment`` in batch mode.
    """

    def __init__(self, cli_executable: str | pathlib.Path | None = None):
        self._cli_explicit = cli_executable
        self._com_app: Any = None

    @property
    def cli_executable(self) -> str:
        return (
            _discover_tool_binary(
                self._cli_explicit,
                ("CST_DE_PATH", "CST_CLI"),
                ("cst_design_environment", "CST DESIGN ENVIRONMENT_AMD64", "CST DESIGN ENVIRONMENT"),
            )
            or "cst_design_environment"
        )

    def connect_com(self, prog_id: str = "CSTStudio.Application") -> Any:
        """Connect to or launch CST Studio Suite via Windows COM."""
        from pycatia3dx.ecosystem.dynamic_com import DynamicCOMObject

        try:
            from win32com.client import Dispatch
        except ImportError as exc:
            raise ImportError("pywin32 is required for CST Studio Suite COM automation.") from exc

        self._com_app = DynamicCOMObject(Dispatch(prog_id))
        return self._com_app

    def open_project_com(self, cst_path: str | pathlib.Path) -> Any:
        """Open an existing ``.cst`` project via COM and return its MWS/Project object."""
        app = self._com_app or self.connect_com()
        return app.open_file(str(pathlib.Path(cst_path).resolve()))

    def run_batch_solver(
        self,
        cst_file: str | pathlib.Path,
        *,
        solver_flag: str = "-m",
        parameter_overrides: Mapping[str, float | int | str] | None = None,
        gpus: int | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """
        Run CST Studio Suite in headless batch mode.

        ``solver_flag`` examples:
        - ``'-m'``: Time-domain (Transient) solver
        - ``'-f'``: Frequency-domain solver
        - ``'-e'``: Eigenmode solver
        - ``'-r'``: Execute embedded VBA macro / parameter sweep
        """
        cmd = [self.cli_executable, solver_flag, str(pathlib.Path(cst_file).resolve())]
        if gpus is not None:
            cmd.append(f"--withgpu={int(gpus)}")
        if parameter_overrides:
            par_expr = ";".join(f"{k}={v}" for k, v in parameter_overrides.items())
            cmd.extend(["-par", par_expr])
        return _exec_tool("SIMULIA CST Studio Suite", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 6. SIMULIA Fluids: PowerFLOW & XFlow (Lattice-Boltzmann CFD)
# ======================================================================
class PowerFlowRunner:
    """Driver for **SIMULIA PowerFLOW** (``pfdiscretize``, ``pfsimulator``, ``exaqsub``)."""

    def __init__(self, executable: str | pathlib.Path | None = None):
        self._explicit = executable

    @property
    def executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("POWERFLOW_CMD", "EXAQSUB_PATH"),
                ("exaqsub", "pfsimulator"),
            )
            or "exaqsub"
        )

    def submit_case(
        self,
        cdi_file: str | pathlib.Path,
        *,
        nprocs: int = 8,
        discretize: bool = True,
        simulate: bool = True,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Submit or run a PowerFLOW ``.cdi`` case."""
        cmd = [self.executable, "-nprocs", str(int(nprocs))]
        if discretize:
            cmd.append("-disc")
        if simulate:
            cmd.append("-sim")
        cmd.append(str(cdi_file))
        return _exec_tool("SIMULIA PowerFLOW", cmd, cwd=cwd, timeout=timeout)


class XFlowRunner:
    """Driver for **SIMULIA XFlow** particle-based Lattice-Boltzmann CFD."""

    def __init__(self, executable: str | pathlib.Path | None = None):
        self._explicit = executable

    @property
    def executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("XFLOW_CMD", "XFLOW_PATH"),
                ("xflow", "xflow-solver"),
            )
            or "xflow"
        )

    def run_project(
        self,
        xfp_file: str | pathlib.Path,
        *,
        generate_domain: bool = True,
        cpus: int | None = None,
        gpus: int | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Run an XFlow ``.xfp`` CFD project headlessly."""
        cmd = [self.executable, str(xfp_file)]
        if generate_domain:
            cmd.append("-gendomain")
        cmd.append("-run")
        if cpus is not None:
            cmd.extend(["-numthreads", str(int(cpus))])
        if gpus is not None:
            cmd.extend(["-gpu", str(int(gpus))])
        return _exec_tool("SIMULIA XFlow", cmd, cwd=cwd, timeout=timeout)


# ======================================================================
# 7. SIMULIA Wave6 (Vibro-Acoustics)
# ======================================================================
class Wave6Runner:
    """Driver for **SIMULIA Wave6** full-frequency vibro-acoustic simulation."""

    def __init__(self, executable: str | pathlib.Path | None = None):
        self._explicit = executable

    @property
    def executable(self) -> str:
        return (
            _discover_tool_binary(
                self._explicit,
                ("WAVE6_CMD", "WAVE6_PATH"),
                ("wave6", "wave6_batch"),
            )
            or "wave6"
        )

    def run_script(
        self,
        script_path: str | pathlib.Path,
        *,
        model_path: str | pathlib.Path | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> SolverProcessResult:
        """Execute a Wave6 automation script in headless batch mode."""
        cmd = [self.executable, "--batch", "--script", str(script_path)]
        if model_path is not None:
            cmd.extend(["--model", str(model_path)])
        return _exec_tool("SIMULIA Wave6", cmd, cwd=cwd, timeout=timeout)
