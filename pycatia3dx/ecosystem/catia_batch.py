"""
3DEXPERIENCE & CATIA Batch / Environment CLI Drivers.

Automates headless & command-line utilities shipped inside ``win_b64/code/bin``:
- ``CATSTART.exe`` (executing any command inside the exact ``CATEnv`` runtime)
- ``CATBatchStarter.exe`` (batch CAD translations STEP/IGES/STL/3DXML/JT, ``CATDUAV5``, PLM import/export)
- ``3DScript.exe`` (CLI execution of 3DEXPERIENCE automation scripts)
- ``3DEXPERIENCE.exe`` (client process launcher)
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Mapping, Sequence

from pycatia3dx.ecosystem.discovery import ThreeDXInstallation, discover_3dx_installations


@dataclass
class BatchExecutionResult:
    """Result of executing a 3DEXPERIENCE CLI / batch utility."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    cwd: pathlib.Path

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


class CATBatchRunner:
    """
    Driver for 3DEXPERIENCE / CATIA command-line and batch utilities
    (``CATSTART``, ``CATBatchStarter``, ``3DScript``, ``3DEXPERIENCE``).
    """

    def __init__(
        self,
        bin_dir: str | pathlib.Path | None = None,
        catenv_name: str | None = None,
        catenv_dir: str | pathlib.Path | None = None,
    ):
        self._explicit_bin_dir = pathlib.Path(bin_dir).resolve() if bin_dir else None
        self.catenv_name = catenv_name
        self.catenv_dir = pathlib.Path(catenv_dir).resolve() if catenv_dir else None

    def _resolve_installation(self) -> ThreeDXInstallation | None:
        installs = discover_3dx_installations()
        for inst in installs:
            if inst.is_running:
                return inst
        return installs[0] if installs else None

    @property
    def bin_dir(self) -> pathlib.Path | None:
        if self._explicit_bin_dir is not None:
            return self._explicit_bin_dir
        inst = self._resolve_installation()
        return inst.bin_dir if inst else None

    def resolve_binary(self, name: str) -> str:
        """Locate a binary inside ``win_b64/code/bin`` or ``PATH``."""
        bdir = self.bin_dir
        try:
            bdir_exists = bool(bdir and bdir.exists())
        except OSError:
            bdir_exists = False
        if bdir and bdir_exists:
            for suffix in ("", ".exe", ".bat", ".cmd"):
                stem = name[:-4] if name.lower().endswith(".exe") else name
                cand = bdir / f"{stem}{suffix}"
                try:
                    if cand.exists():
                        return str(cand)
                except OSError:
                    continue
        found = shutil.which(name)
        return found or name

    def _resolve_env_args(self) -> list[str]:
        env_name = self.catenv_name
        env_dir = self.catenv_dir
        if (env_name is None or env_dir is None):
            inst = self._resolve_installation()
            if inst and inst.catenv_files:
                first_env = inst.catenv_files[0]
                env_name = env_name or first_env.stem
                env_dir = env_dir or first_env.parent
        args: list[str] = []
        if env_name:
            args.extend(["-env", env_name])
        if env_dir:
            args.extend(["-direnv", str(env_dir)])
        return args

    def build_catstart_command(
        self,
        run_command: str,
        *,
        nowindow: bool = True,
    ) -> list[str]:
        """Build a ``CATSTART -run "..." -env ... -direnv ...`` command list."""
        cmd = [self.resolve_binary("CATSTART"), "-run", run_command, *self._resolve_env_args()]
        if nowindow:
            cmd.append("-nowindow")
        return cmd

    def run_in_catenv(
        self,
        run_command: str,
        *,
        nowindow: bool = True,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> BatchExecutionResult:
        """Execute any 3DEXPERIENCE binary or tool inside ``CATSTART``'s runtime environment."""
        cmd = self.build_catstart_command(run_command, nowindow=nowindow)
        return self._exec(cmd, cwd=cwd, timeout=timeout, env=env)

    @staticmethod
    def build_batch_xml(
        batch_descriptor_name: str,
        parameters: Mapping[str, str],
        *,
        file_inputs: Sequence[str | pathlib.Path] = (),
        output_folder: str | pathlib.Path | None = None,
    ) -> str:
        """Build a ``CATBatchStarter`` XML parameter file."""
        root = ET.Element("batch", attrib={"name": batch_descriptor_name})
        for key, value in parameters.items():
            ET.SubElement(root, "param", attrib={"name": key, "value": str(value)})
        for fpath in file_inputs:
            ET.SubElement(root, "file", attrib={"path": str(pathlib.Path(fpath).resolve())})
        if output_folder is not None:
            ET.SubElement(
                root,
                "output",
                attrib={"folder": str(pathlib.Path(output_folder).resolve())},
            )
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"

    def run_batch_starter(
        self,
        input_xml_path: str | pathlib.Path,
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> BatchExecutionResult:
        """Execute ``CATBatchStarter -input <xml>``."""
        cmd = [
            self.resolve_binary("CATBatchStarter"),
            "-input",
            str(pathlib.Path(input_xml_path).resolve()),
        ]
        return self._exec(cmd, cwd=cwd, timeout=timeout)

    def run_cad_translation_batch(
        self,
        input_files: Sequence[str | pathlib.Path],
        output_folder: str | pathlib.Path,
        *,
        target_format: str = "STEP",
        batch_descriptor: str = "BatchDXFIGESSTEP",
        timeout: float | None = None,
    ) -> BatchExecutionResult:
        """Generate a temporary batch XML and execute CAD format conversion via ``CATBatchStarter``."""
        xml_text = self.build_batch_xml(
            batch_descriptor,
            {"TargetFormat": target_format.upper()},
            file_inputs=input_files,
            output_folder=output_folder,
        )
        with tempfile.TemporaryDirectory(prefix="pycatia3dx_batch_") as tmp:
            xml_path = pathlib.Path(tmp) / "batch_params.xml"
            xml_path.write_text(xml_text, encoding="utf-8")
            return self.run_batch_starter(xml_path, timeout=timeout)

    def run_3dscript(
        self,
        script_path: str | pathlib.Path,
        script_args: Sequence[str] = (),
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> BatchExecutionResult:
        """Execute a ``.3dscript`` / automation script via ``3DScript`` CLI."""
        cmd = [
            self.resolve_binary("3DScript"),
            str(pathlib.Path(script_path).resolve()),
            *(str(a) for a in script_args),
        ]
        return self._exec(cmd, cwd=cwd, timeout=timeout)

    def launch_3dexperience_client(
        self,
        extra_args: Sequence[str] = (),
        *,
        cwd: str | pathlib.Path | None = None,
    ) -> subprocess.Popen[bytes]:
        """Launch ``3DEXPERIENCE.exe`` asynchronously and return its ``Popen`` handle."""
        exe = self.resolve_binary("3DEXPERIENCE")
        cmd = [exe, *self._resolve_env_args(), *(str(a) for a in extra_args)]
        work_dir = str(pathlib.Path(cwd).resolve()) if cwd else None
        return subprocess.Popen(cmd, cwd=work_dir)

    @staticmethod
    def _exec(
        cmd: list[str],
        *,
        cwd: str | pathlib.Path | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> BatchExecutionResult:
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
                f"3DEXPERIENCE CLI utility {cmd[0]!r} was not found. Pass bin_dir=... to CATBatchRunner()."
            ) from exc
        return BatchExecutionResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cwd=work_dir,
        )
