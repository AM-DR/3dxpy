"""
Abaqus & 3DEXPERIENCE Embedded Solver Driver + Abaqus Python/CAE Scripting Bridge.

Supports:
- Automatic discovery of standalone SIMULIA Abaqus (``abaqus``, ``abq2024``–``abq2026``)
  and 3DEXPERIENCE embedded solver launchers (``ABQLauncher``, ``SMALauncher``).
- Executing, monitoring, suspending, resuming, and terminating Abaqus/Standard,
  Abaqus/Explicit, and CFD/Thermal solver jobs.
- Parsing ``.sta``, ``.msg``, and ``.dat`` solver output files into structured
  Python objects (step/increment convergence history, warnings, and errors).
- Driving Abaqus's own Python interpreter (``abaqus python``, ``abaqus cae noGUI=...``,
  ``abaqus viewer noGUI=...``) including seamless **inline Python function/script
  execution** with automatic JSON payload/result marshaling between external
  Python 3.11–3.14 and Abaqus's internal ``mdb`` / ``session`` / ``odbAccess`` runtime.
"""
from __future__ import annotations

import inspect
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence


@dataclass
class AbaqusIncrement:
    """Single increment entry parsed from an Abaqus ``.sta`` status file."""

    step: int
    increment: int
    attempt: str
    severe_discontinuities: int
    equilibrium_iters: int
    total_iters: int
    total_time: float
    step_time: float
    time_increment: float


@dataclass
class AbaqusJobStatus:
    """Parsed solver status and diagnostics for an Abaqus job."""

    job_name: str
    completed: bool = False
    failed: bool = False
    running: bool = False
    status_text: str = "UNKNOWN"
    increments: list[AbaqusIncrement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    sta_path: pathlib.Path | None = None
    msg_path: pathlib.Path | None = None
    dat_path: pathlib.Path | None = None
    odb_path: pathlib.Path | None = None
    log_path: pathlib.Path | None = None


@dataclass
class AbaqusCommandResult:
    """Result of invoking an Abaqus CLI, solver job, or CAE/Python script."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    cwd: pathlib.Path
    job_status: AbaqusJobStatus | None = None
    output_data: Any = None

    @property
    def succeeded(self) -> bool:
        if self.returncode != 0:
            return False
        if self.job_status is not None and self.job_status.failed:
            return False
        return True


_STA_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
    r"([+-]?\d+(?:\.\d+)?(?:[eEdD][+-]?\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?(?:[eEdD][+-]?\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?(?:[eEdD][+-]?\d+)?)"
)


def _parse_float(token: str) -> float:
    return float(token.replace("D", "E").replace("d", "e"))


def parse_sta_file(sta_path: str | pathlib.Path) -> AbaqusJobStatus:
    """Parse an Abaqus ``.sta`` status file into an :class:`AbaqusJobStatus`."""
    p = pathlib.Path(sta_path)
    status = AbaqusJobStatus(job_name=p.stem, sta_path=p if p.exists() else None)
    if not p.exists():
        return status

    text = p.read_text(encoding="utf-8", errors="replace")
    upper = text.upper()

    if "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in upper:
        status.completed = True
        status.failed = False
        status.running = False
        status.status_text = "COMPLETED"
    elif "THE ANALYSIS HAS NOT BEEN COMPLETED" in upper:
        status.completed = False
        status.failed = True
        status.running = False
        status.status_text = "FAILED"
    else:
        status.running = True
        status.status_text = "RUNNING"

    for line in text.splitlines():
        m = _STA_ROW_RE.match(line)
        if m:
            status.increments.append(
                AbaqusIncrement(
                    step=int(m.group(1)),
                    increment=int(m.group(2)),
                    attempt=m.group(3),
                    severe_discontinuities=int(m.group(4)),
                    equilibrium_iters=int(m.group(5)),
                    total_iters=int(m.group(6)),
                    total_time=_parse_float(m.group(7)),
                    step_time=_parse_float(m.group(8)),
                    time_increment=_parse_float(m.group(9)),
                )
            )
    return status


def _extract_diagnostics(text: str) -> tuple[list[str], list[str]]:
    """Extract ``***WARNING`` and ``***ERROR`` blocks from ``.msg`` / ``.dat`` / ``.log``."""
    warnings: list[str] = []
    errors: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        upper = stripped.upper()
        if upper.startswith("***WARNING") or upper.startswith("*** WARNING"):
            block = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("***"):
                block.append(lines[i].strip())
                i += 1
            warnings.append(" ".join(block))
            continue
        if upper.startswith("***ERROR") or upper.startswith("*** ERROR") or "ABAQUS/STANDARD EXITED WITH AN ERROR" in upper or "ABAQUS/EXPLICIT EXITED WITH AN ERROR" in upper:
            block = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("***"):
                block.append(lines[i].strip())
                i += 1
            errors.append(" ".join(block))
            continue
        i += 1
    return warnings, errors


def parse_msg_file(msg_path: str | pathlib.Path) -> tuple[list[str], list[str]]:
    """Return ``(warnings, errors)`` from an Abaqus ``.msg`` file."""
    p = pathlib.Path(msg_path)
    if not p.exists():
        return [], []
    return _extract_diagnostics(p.read_text(encoding="utf-8", errors="replace"))


def parse_dat_file(dat_path: str | pathlib.Path) -> tuple[list[str], list[str]]:
    """Return ``(warnings, errors)`` from an Abaqus ``.dat`` file."""
    p = pathlib.Path(dat_path)
    if not p.exists():
        return [], []
    return _extract_diagnostics(p.read_text(encoding="utf-8", errors="replace"))


def inspect_job_files(job_name: str, directory: str | pathlib.Path = ".") -> AbaqusJobStatus:
    """Inspect ``.sta``, ``.msg``, ``.dat``, ``.log``, and ``.odb`` files for ``job_name``."""
    base = pathlib.Path(directory).resolve()
    sta = base / f"{job_name}.sta"
    msg = base / f"{job_name}.msg"
    dat = base / f"{job_name}.dat"
    odb = base / f"{job_name}.odb"
    log = base / f"{job_name}.log"
    lck = base / f"{job_name}.lck"

    status = parse_sta_file(sta)
    status.job_name = job_name
    status.msg_path = msg if msg.exists() else None
    status.dat_path = dat if dat.exists() else None
    status.odb_path = odb if odb.exists() else None
    status.log_path = log if log.exists() else None

    for diag_file in (dat, msg, log):
        if diag_file.exists():
            w, e = _extract_diagnostics(diag_file.read_text(encoding="utf-8", errors="replace"))
            for item in w:
                if item not in status.warnings:
                    status.warnings.append(item)
            for item in e:
                if item not in status.errors:
                    status.errors.append(item)

    if lck.exists() and not status.completed and not status.failed:
        status.running = True
        status.status_text = "RUNNING"
    elif status.errors and not status.completed:
        status.failed = True
        status.running = False
        status.status_text = "FAILED"
    elif log.exists() and not sta.exists():
        log_upper = log.read_text(encoding="utf-8", errors="replace").upper()
        if "COMPLETED" in log_upper and "ERROR" not in log_upper:
            status.completed = True
            status.status_text = "COMPLETED"
        elif "EXITED WITH ERRORS" in log_upper or "EXITED WITH AN ERROR" in log_upper:
            status.failed = True
            status.status_text = "FAILED"

    return status


_ABAQUS_CANDIDATE_NAMES = (
    "abaqus",
    "abq2026",
    "abq2025",
    "abq2024",
    "abq2023",
    "abq2022",
    "abq2021",
    "abq2020",
    "ABQLauncher",
    "SMALauncher",
)


def _safe_exists(p: pathlib.Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


def _safe_iterdir(p: pathlib.Path) -> list[pathlib.Path]:
    try:
        return list(p.iterdir())
    except OSError:
        return []


def find_abaqus_executable(explicit_path: str | pathlib.Path | None = None) -> str | None:
    """
    Auto-discover an Abaqus or 3DEXPERIENCE SIMULIA solver launcher executable.

    Checks (in order):
    1. ``explicit_path`` argument
    2. ``ABAQUS_BAT_PATH``, ``ABAQUS_COMMAND``, or ``ABQ_LAUNCHER`` environment variables
    3. Executables on ``PATH`` (``abaqus``, ``abq2026``..``abq2020``, ``ABQLauncher``, ``SMALauncher``)
    4. Standard SIMULIA & 3DEXPERIENCE installation folders on Windows and Linux
    """
    if explicit_path:
        p = pathlib.Path(explicit_path)
        if _safe_exists(p):
            return str(p)
        resolved = shutil.which(str(explicit_path))
        if resolved:
            return resolved
        return str(explicit_path)

    for env_var in ("ABAQUS_BAT_PATH", "ABAQUS_COMMAND", "ABQ_LAUNCHER"):
        val = os.environ.get(env_var)
        if val:
            if _safe_exists(pathlib.Path(val)):
                return val
            resolved = shutil.which(val)
            if resolved:
                return resolved

    for name in _ABAQUS_CANDIDATE_NAMES:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    search_dirs: list[pathlib.Path] = []
    if sys.platform == "win32":
        for drive in ("C:\\", "D:\\"):
            d_path = pathlib.Path(drive)
            search_dirs.extend([
                d_path / "SIMULIA" / "Commands",
                d_path / "Program Files" / "Dassault Systemes" / "SIMULIA" / "Commands",
            ])
            ds_root = d_path / "Program Files" / "Dassault Systemes"
            if _safe_exists(ds_root):
                for child in sorted(_safe_iterdir(ds_root), reverse=True):
                    bin_dir = child / "win_b64" / "code" / "bin"
                    if _safe_exists(bin_dir):
                        search_dirs.append(bin_dir)
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            la_ds = pathlib.Path(local_app) / "DassaultSystemes"
            if _safe_exists(la_ds):
                for child in sorted(_safe_iterdir(la_ds), reverse=True):
                    bin_dir = child / "win_b64" / "code" / "bin"
                    if _safe_exists(bin_dir):
                        search_dirs.append(bin_dir)
    else:
        search_dirs.extend([
            pathlib.Path("/var/DassaultSystemes/SIMULIA/Commands"),
            pathlib.Path("/opt/SIMULIA/Commands"),
            pathlib.Path("/usr/SIMULIA/Commands"),
            pathlib.Path("/usr/DassaultSystemes/SIMULIA/Commands"),
        ])

    exts = (".bat", ".cmd", ".exe", "") if sys.platform == "win32" else ("",)
    for folder in search_dirs:
        if not _safe_exists(folder):
            continue
        for name in _ABAQUS_CANDIDATE_NAMES:
            for ext in exts:
                cand = folder / f"{name}{ext}"
                if _safe_exists(cand):
                    return str(cand)

    return None


class AbaqusRunner:
    """
    High-level Python controller for Abaqus solvers, CAE/Viewer headless
    automation, and Abaqus's embedded Python runtime.

    Example::

        from pycatia3dx.simulia import AbaqusRunner

        abq = AbaqusRunner()
        res = abq.run_job("bracket_static", input_file="bracket.inp", cpus=4)
        print(res.job_status.completed, len(res.job_status.increments))
    """

    def __init__(
        self,
        executable: str | pathlib.Path | None = None,
        default_cwd: str | pathlib.Path | None = None,
    ):
        self._explicit_executable = str(executable) if executable else None
        self.default_cwd = pathlib.Path(default_cwd).resolve() if default_cwd else None

    @property
    def executable(self) -> str:
        """Resolved Abaqus command path (falls back to ``'abaqus'`` if not yet on disk)."""
        found = find_abaqus_executable(self._explicit_executable)
        return found or (self._explicit_executable or "abaqus")

    def is_available(self) -> bool:
        """Return ``True`` if an Abaqus / SIMULIA solver executable was found."""
        found = find_abaqus_executable(self._explicit_executable)
        if not found:
            return False
        return pathlib.Path(found).exists() or shutil.which(found) is not None

    def build_job_command(
        self,
        job: str,
        input_file: str | pathlib.Path | None = None,
        *,
        cpus: int | None = None,
        gpus: int | None = None,
        memory: str | None = None,
        mp_mode: str | None = None,
        double_precision: str | None = None,
        user_subroutine: str | pathlib.Path | None = None,
        oldjob: str | None = None,
        globalmodel: str | pathlib.Path | None = None,
        scratch: str | pathlib.Path | None = None,
        queue: str | None = None,
        interactive: bool = True,
        ask_delete: bool = False,
        datacheck: bool = False,
        continue_analysis: bool = False,
        recover: bool = False,
        extra_args: Sequence[str] = (),
    ) -> list[str]:
        """Construct an Abaqus solver CLI argument list."""
        cmd: list[str] = [self.executable, f"job={job}"]
        if input_file is not None:
            inp_str = str(input_file)
            if inp_str.lower().endswith(".inp"):
                inp_str = inp_str[:-4]
            cmd.append(f"input={inp_str}")
        if cpus is not None:
            cmd.append(f"cpus={int(cpus)}")
        if gpus is not None:
            cmd.append(f"gpus={int(gpus)}")
        if memory is not None:
            cmd.append(f"memory={memory}")
        if mp_mode is not None:
            cmd.append(f"mp_mode={mp_mode}")
        if double_precision is not None:
            if double_precision == "both":
                cmd.extend(["double=both"])
            elif double_precision in ("analysis", "explicit", "constraint", "off"):
                cmd.append(f"double={double_precision}")
            else:
                cmd.append("double")
        if user_subroutine is not None:
            cmd.append(f"user={user_subroutine}")
        if oldjob is not None:
            cmd.append(f"oldjob={oldjob}")
        if globalmodel is not None:
            cmd.append(f"globalmodel={globalmodel}")
        if scratch is not None:
            cmd.append(f"scratch={scratch}")
        if queue is not None:
            cmd.append(f"queue={queue}")
        if datacheck:
            cmd.append("datacheck")
        if continue_analysis:
            cmd.append("continue")
        if recover:
            cmd.append("recover")
        if interactive:
            cmd.append("interactive")
        if not ask_delete:
            cmd.append("ask_delete=OFF")
        cmd.extend(extra_args)
        return cmd

    def _run_subprocess(
        self,
        cmd: list[str],
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        work_dir = pathlib.Path(cwd).resolve() if cwd else (self.default_cwd or pathlib.Path.cwd())
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        try:
            return subprocess.run(
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
                f"Abaqus executable {cmd[0]!r} was not found. Set ABAQUS_BAT_PATH or pass "
                f"executable=... to AbaqusRunner()."
            ) from exc

    def run_job(
        self,
        job: str,
        input_file: str | pathlib.Path | None = None,
        *,
        cpus: int | None = None,
        gpus: int | None = None,
        memory: str | None = None,
        mp_mode: str | None = None,
        double_precision: str | None = None,
        user_subroutine: str | pathlib.Path | None = None,
        oldjob: str | pathlib.Path | None = None,
        globalmodel: str | pathlib.Path | None = None,
        scratch: str | pathlib.Path | None = None,
        queue: str | None = None,
        interactive: bool = True,
        ask_delete: bool = False,
        datacheck: bool = False,
        continue_analysis: bool = False,
        recover: bool = False,
        extra_args: Sequence[str] = (),
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> AbaqusCommandResult:
        """Execute an Abaqus solver job and parse its resulting ``.sta``/``.msg``/``.dat`` files."""
        work_dir = pathlib.Path(cwd).resolve() if cwd else (self.default_cwd or pathlib.Path.cwd())
        cmd = self.build_job_command(
            job,
            input_file,
            cpus=cpus,
            gpus=gpus,
            memory=memory,
            mp_mode=mp_mode,
            double_precision=double_precision,
            user_subroutine=user_subroutine,
            oldjob=str(oldjob) if oldjob else None,
            globalmodel=globalmodel,
            scratch=scratch,
            queue=queue,
            interactive=interactive,
            ask_delete=ask_delete,
            datacheck=datacheck,
            continue_analysis=continue_analysis,
            recover=recover,
            extra_args=extra_args,
        )
        proc = self._run_subprocess(cmd, cwd=work_dir, timeout=timeout, env=env)
        status = inspect_job_files(job, work_dir)
        return AbaqusCommandResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cwd=work_dir,
            job_status=status,
        )

    def datacheck(
        self,
        job: str,
        input_file: str | pathlib.Path | None = None,
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> AbaqusCommandResult:
        """Run an Abaqus input-deck ``datacheck`` validation without full solve."""
        return self.run_job(job, input_file, datacheck=True, cwd=cwd, timeout=timeout)

    def continue_job(
        self,
        job: str,
        *,
        cpus: int | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> AbaqusCommandResult:
        """Continue an analysis after a prior ``datacheck``."""
        return self.run_job(job, cpus=cpus, continue_analysis=True, cwd=cwd, timeout=timeout)

    def _job_control_action(
        self,
        action: str,
        job: str,
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = 60.0,
    ) -> AbaqusCommandResult:
        work_dir = pathlib.Path(cwd).resolve() if cwd else (self.default_cwd or pathlib.Path.cwd())
        cmd = [self.executable, action, f"job={job}"]
        proc = self._run_subprocess(cmd, cwd=work_dir, timeout=timeout)
        return AbaqusCommandResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cwd=work_dir,
            job_status=inspect_job_files(job, work_dir),
        )

    def terminate_job(self, job: str, *, cwd: str | pathlib.Path | None = None) -> AbaqusCommandResult:
        """Send graceful ``terminate`` signal to a running Abaqus job."""
        return self._job_control_action("terminate", job, cwd=cwd)

    def suspend_job(self, job: str, *, cwd: str | pathlib.Path | None = None) -> AbaqusCommandResult:
        """Suspend a running Abaqus job (releasing solver license tokens)."""
        return self._job_control_action("suspend", job, cwd=cwd)

    def resume_job(self, job: str, *, cwd: str | pathlib.Path | None = None) -> AbaqusCommandResult:
        """Resume a previously suspended Abaqus job."""
        return self._job_control_action("resume", job, cwd=cwd)

    def upgrade_odb(
        self,
        source_odb: str | pathlib.Path,
        target_job: str,
        *,
        cwd: str | pathlib.Path | None = None,
    ) -> AbaqusCommandResult:
        """Upgrade a legacy ``.odb`` file to the current Abaqus release."""
        work_dir = pathlib.Path(cwd).resolve() if cwd else (self.default_cwd or pathlib.Path.cwd())
        cmd = [self.executable, "-upgrade", f"-job={target_job}", f"-odb={source_odb}"]
        proc = self._run_subprocess(cmd, cwd=work_dir)
        return AbaqusCommandResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cwd=work_dir,
        )

    def run_python_script(
        self,
        script_path: str | pathlib.Path,
        script_args: Sequence[str] = (),
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> AbaqusCommandResult:
        """
        Execute a Python script inside Abaqus's standalone Python interpreter
        (``abaqus python <script.py> [args]`` — supports ``odbAccess``, math/numpy,
        without checking out an Abaqus/CAE GUI token).
        """
        work_dir = pathlib.Path(cwd).resolve() if cwd else (self.default_cwd or pathlib.Path.cwd())
        cmd = [self.executable, "python", str(script_path), *[str(a) for a in script_args]]
        proc = self._run_subprocess(cmd, cwd=work_dir, timeout=timeout, env=env)
        return AbaqusCommandResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cwd=work_dir,
        )

    def run_cae_script(
        self,
        script_path: str | pathlib.Path,
        script_args: Sequence[str] = (),
        *,
        gui: bool = False,
        database: str | pathlib.Path | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> AbaqusCommandResult:
        """
        Execute an Abaqus/CAE modeling & meshing Python script
        (``abaqus cae noGUI=<script.py> -- [args]`` or ``script=<script.py>``).
        """
        work_dir = pathlib.Path(cwd).resolve() if cwd else (self.default_cwd or pathlib.Path.cwd())
        mode_flag = f"script={script_path}" if gui else f"noGUI={script_path}"
        cmd = [self.executable, "cae", mode_flag]
        if database is not None:
            cmd.append(f"database={database}")
        if script_args:
            cmd.append("--")
            cmd.extend(str(a) for a in script_args)
        proc = self._run_subprocess(cmd, cwd=work_dir, timeout=timeout, env=env)
        return AbaqusCommandResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cwd=work_dir,
        )

    def run_viewer_script(
        self,
        script_path: str | pathlib.Path,
        script_args: Sequence[str] = (),
        *,
        gui: bool = False,
        database: str | pathlib.Path | None = None,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> AbaqusCommandResult:
        """
        Execute an Abaqus/Viewer post-processing script
        (``abaqus viewer noGUI=<script.py> -- [args]``).
        """
        work_dir = pathlib.Path(cwd).resolve() if cwd else (self.default_cwd or pathlib.Path.cwd())
        mode_flag = f"script={script_path}" if gui else f"noGUI={script_path}"
        cmd = [self.executable, "viewer", mode_flag]
        if database is not None:
            cmd.append(f"database={database}")
        if script_args:
            cmd.append("--")
            cmd.extend(str(a) for a in script_args)
        proc = self._run_subprocess(cmd, cwd=work_dir, timeout=timeout, env=env)
        return AbaqusCommandResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cwd=work_dir,
        )

    @staticmethod
    def build_inline_bootstrap(
        code_or_func: str | Callable[[dict[str, Any]], Any],
        input_json_path: str | pathlib.Path,
        output_json_path: str | pathlib.Path,
    ) -> str:
        """
        Generate a Python 2.7 & 3.x compatible wrapper script to execute inside
        Abaqus's internal Python runtime and marshal JSON input/output.
        """
        in_path_literal = repr(str(pathlib.Path(input_json_path).resolve()))
        out_path_literal = repr(str(pathlib.Path(output_json_path).resolve()))

        if callable(code_or_func):
            src = textwrap.dedent(inspect.getsource(code_or_func))
            func_name = code_or_func.__name__
            user_block = f"{src}\n\nRESULT = {func_name}(PAYLOAD)\n"
        else:
            user_block = textwrap.dedent(code_or_func)

        indented_user = textwrap.indent(user_block, "    ")
        # Written carefully so both legacy Abaqus Python 2.7 and modern Abaqus Python 3.10+ parse it.
        return (
            "# -*- coding: utf-8 -*-\n"
            "import io\n"
            "import json\n"
            "import traceback\n\n"
            f"_IN_PATH = {in_path_literal}\n"
            f"_OUT_PATH = {out_path_literal}\n\n"
            "with io.open(_IN_PATH, 'r', encoding='utf-8') as _f:\n"
            "    PAYLOAD = json.loads(_f.read())\n\n"
            "RESULT = None\n"
            "_envelope = {'ok': True, 'result': None, 'error': None, 'traceback': None}\n"
            "try:\n"
            f"{indented_user}\n"
            "    _envelope['result'] = RESULT\n"
            "except Exception as _exc:\n"
            "    _envelope['ok'] = False\n"
            "    _envelope['error'] = str(_exc)\n"
            "    _envelope['traceback'] = traceback.format_exc()\n\n"
            "with io.open(_OUT_PATH, 'w', encoding='utf-8') as _f:\n"
            "    _txt = json.dumps(_envelope)\n"
            "    try:\n"
            "        _txt = unicode(_txt)\n"
            "    except NameError:\n"
            "        pass\n"
            "    _f.write(_txt)\n"
        )

    def execute_inline(
        self,
        code_or_func: str | Callable[[dict[str, Any]], Any],
        payload: Mapping[str, Any] | None = None,
        *,
        mode: str = "cae",
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> AbaqusCommandResult:
        """
        Execute a Python function or script block directly inside Abaqus's own
        Python interpreter (``mode='cae'``, ``'python'``, or ``'viewer'``) and
        return the JSON-marshaled result on ``result.output_data``.

        Example::

            def build_block_in_cae(payload):
                from abaqus import mdb
                model = mdb.models["Model-1"]
                s = model.ConstrainedSketch(name="profile", sheetSize=200.0)
                s.rectangle(point1=(0.0, 0.0), point2=(payload["w"], payload["h"]))
                p = model.Part(name="Block", dimensionality=3, type=1)
                p.BaseSolidExtrude(sketch=s, depth=payload["depth"])
                mdb.saveAs(pathName=payload["cae_path"])
                return {"parts": list(model.parts.keys())}

            res = abq.execute_inline(
                build_block_in_cae,
                {"w": 50.0, "h": 30.0, "depth": 10.0, "cae_path": "block.cae"},
                mode="cae",
            )
            print(res.output_data)
        """
        if mode not in ("cae", "python", "viewer"):
            raise ValueError(f"mode must be 'cae', 'python', or 'viewer'; got {mode!r}")

        with tempfile.TemporaryDirectory(prefix="pycatia3dx_abq_") as tmp:
            tmp_dir = pathlib.Path(tmp)
            in_json = tmp_dir / "input.json"
            out_json = tmp_dir / "output.json"
            script_py = tmp_dir / "inline_abaqus_task.py"

            in_json.write_text(json.dumps(dict(payload or {})), encoding="utf-8")
            script_py.write_text(
                self.build_inline_bootstrap(code_or_func, in_json, out_json),
                encoding="utf-8",
            )

            if mode == "cae":
                cmd_res = self.run_cae_script(script_py, gui=False, cwd=cwd, timeout=timeout, env=env)
            elif mode == "viewer":
                cmd_res = self.run_viewer_script(script_py, gui=False, cwd=cwd, timeout=timeout, env=env)
            else:
                cmd_res = self.run_python_script(script_py, cwd=cwd, timeout=timeout, env=env)

            if out_json.exists():
                envelope = json.loads(out_json.read_text(encoding="utf-8"))
                if not envelope.get("ok", False):
                    raise RuntimeError(
                        f"Abaqus inline {mode} script raised an exception: "
                        f"{envelope.get('error')}\n{envelope.get('traceback')}"
                    )
                cmd_res.output_data = envelope.get("result")

            return cmd_res
