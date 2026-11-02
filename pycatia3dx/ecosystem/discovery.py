"""
3DEXPERIENCE & Dassault Systèmes Installation, CATEnv, and Process Discovery.

Locates all installed 3DEXPERIENCE releases (``B424``–``B429``, ``B428_Cloud``,
``R2022x``–``R2026x``), ``win_b64/code/bin`` directories, ``CATEnv`` environment
files, standalone brand tools (SIMULIA, DELMIA, BIOVIA, GEOVIA, CST, SOLIDWORKS),
and currently running processes.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass, field

from pycatia3dx.simulia.abaqus import find_abaqus_executable


def _safe_exists(p: pathlib.Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


def _safe_is_dir(p: pathlib.Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False


def _safe_iterdir(p: pathlib.Path) -> list[pathlib.Path]:
    try:
        return list(p.iterdir())
    except OSError:
        return []


def _safe_glob(p: pathlib.Path, pattern: str) -> list[pathlib.Path]:
    try:
        return list(p.glob(pattern))
    except OSError:
        return []


@dataclass
class ThreeDXInstallation:
    """Metadata describing a discovered Dassault Systèmes / 3DEXPERIENCE installation."""

    name: str
    root_dir: pathlib.Path
    bin_dir: pathlib.Path | None = None
    catenv_files: list[pathlib.Path] = field(default_factory=list)
    com3dx_path: pathlib.Path | None = None
    is_running: bool = False

    def find_executable(self, binary_name: str) -> pathlib.Path | None:
        if self.bin_dir is None or not _safe_exists(self.bin_dir):
            return None
        exts = ("", ".exe", ".bat", ".cmd") if sys.platform == "win32" else ("",)
        stem = binary_name[:-4] if binary_name.lower().endswith(".exe") else binary_name
        for ext in exts:
            cand = self.bin_dir / f"{stem}{ext}"
            if _safe_exists(cand):
                return cand
        return None


def _collect_catenv_files() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    roots: list[pathlib.Path] = []
    if sys.platform == "win32":
        prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
        local_app = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        for base in (prog_data, local_app, appdata):
            if base:
                roots.append(pathlib.Path(base) / "DassaultSystemes" / "CATEnv")
    else:
        home = pathlib.Path.home()
        roots.extend([
            home / "CATEnv",
            pathlib.Path("/var/DassaultSystemes/CATEnv"),
        ])

    for folder in roots:
        if _safe_exists(folder):
            found.extend(sorted(_safe_glob(folder, "*.txt")))
    return found


def discover_3dx_installations() -> list[ThreeDXInstallation]:
    """
    Scan running processes and standard Dassault Systèmes directories for
    3DEXPERIENCE / CATIA / DELMIA / SIMULIA installations.
    """
    installations: dict[pathlib.Path, ThreeDXInstallation] = {}
    all_catenvs = _collect_catenv_files()

    from pycatia3dx.base_interfaces.base_application import _iter_3dx_process_executables

    _, running_exes = _iter_3dx_process_executables()
    for exe_str in running_exes:
        exe_path = pathlib.Path(exe_str)
        # Typically <ROOT>/win_b64/code/bin/3DEXPERIENCE.exe
        bin_dir = exe_path.parent
        root_dir = bin_dir.parent.parent.parent if bin_dir.name.lower() == "bin" else bin_dir
        com3dx = bin_dir.parent / "python3dx" / "lib" / "com3dx.py"
        installations[root_dir] = ThreeDXInstallation(
            name=root_dir.name,
            root_dir=root_dir,
            bin_dir=bin_dir,
            catenv_files=all_catenvs,
            com3dx_path=com3dx if _safe_exists(com3dx) else None,
            is_running=True,
        )

    candidate_parents: list[pathlib.Path] = []
    if sys.platform == "win32":
        for drive in ("C:\\", "D:\\"):
            d = pathlib.Path(drive)
            candidate_parents.extend([
                d / "Program Files" / "Dassault Systemes",
                d / "Dassault Systemes",
            ])
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidate_parents.append(pathlib.Path(local_app) / "DassaultSystemes")
    else:
        candidate_parents.extend([
            pathlib.Path("/usr/DassaultSystemes"),
            pathlib.Path("/opt/DassaultSystemes"),
        ])

    arch_folders = ("win_b64", "linux_a64")
    for parent in candidate_parents:
        if not _safe_exists(parent):
            continue
        for child in sorted(_safe_iterdir(parent), reverse=True):
            if not _safe_is_dir(child) or child in installations:
                continue
            for arch in arch_folders:
                bin_dir = child / arch / "code" / "bin"
                if _safe_exists(bin_dir):
                    com3dx = child / arch / "code" / "python3dx" / "lib" / "com3dx.py"
                    installations[child] = ThreeDXInstallation(
                        name=child.name,
                        root_dir=child,
                        bin_dir=bin_dir,
                        catenv_files=all_catenvs,
                        com3dx_path=com3dx if _safe_exists(com3dx) else None,
                        is_running=False,
                    )
                    break

    return list(installations.values())


def discover_ecosystem_summary() -> dict[str, object]:
    """Return a diagnostic dictionary of discovered 3DEXPERIENCE & solver installations."""
    installs = discover_3dx_installations()
    return {
        "3dexperience_installations": [
            {
                "name": inst.name,
                "root_dir": str(inst.root_dir),
                "bin_dir": str(inst.bin_dir) if inst.bin_dir else None,
                "com3dx_available": inst.com3dx_path is not None,
                "is_running": inst.is_running,
            }
            for inst in installs
        ],
        "abaqus_executable": find_abaqus_executable(),
        "catenv_files": [str(p) for p in _collect_catenv_files()],
    }
