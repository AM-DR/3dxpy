from __future__ import annotations

import builtins
import importlib.machinery
import importlib.util
import logging
import pathlib
import sys
from types import ModuleType
from typing import Callable

logger = logging.getLogger(__name__)

# Name under which the Dassault Systèmes module is registered in sys.modules.
_COM3DX_MODULE_NAME = "com3dx"

# Name of the replacement hasattr function installed by com3dx.py.
_COM3DX_HASATTR_NAME = "dbcHasattr"

# Keep a reference to the genuine builtin hasattr as early as possible (i.e.
# when pycatia3dx is imported), before com3dx.py gets the chance to patch it.
_BUILTIN_HASATTR: Callable[[object, str], bool] | None = (
    builtins.hasattr if getattr(builtins.hasattr, "__name__", "") != _COM3DX_HASATTR_NAME else None
)


def _pure_python_hasattr(obj: object, name: str) -> bool:
    """
    Exact behavioural equivalent of the builtin :func:`hasattr`.

    Used as a last resort when the genuine builtin cannot be recovered because
    another module has already replaced ``builtins.hasattr``.
    """
    try:
        getattr(obj, name)
    except AttributeError:
        return False
    return True


def _original_hasattr() -> Callable[[object, str], bool]:
    """
    Return the genuine (un-patched) :func:`hasattr` function.

    ``com3dx.py`` replaces ``builtins.hasattr`` with its own ``dbcHasattr``
    which delegates to a module global ``_builtin_hasattr``. That global is only
    assigned when ``builtins.hasattr`` has not been patched yet. If the module
    is executed a second time (for example because it was imported by another
    tool, by a different module name, or by an older pycatia3dx version) the
    global is never assigned and every ``hasattr`` call in the process raises
    ``NameError: name '_builtin_hasattr' is not defined``.

    This function follows the chain of patched functions back to the original.
    """
    if _BUILTIN_HASATTR is not None:
        return _BUILTIN_HASATTR

    current = builtins.hasattr
    seen: set[int] = set()
    while getattr(current, "__name__", "") == _COM3DX_HASATTR_NAME and id(current) not in seen:
        seen.add(id(current))
        nxt = getattr(current, "__globals__", {}).get("_builtin_hasattr")
        if nxt is None:
            return _pure_python_hasattr
        current = nxt

    if getattr(current, "__name__", "") == _COM3DX_HASATTR_NAME:
        return _pure_python_hasattr
    return current


def _repair_patched_hasattr() -> None:
    """
    Make sure that every ``dbcHasattr`` currently installed (or reachable
    through the chain of patched functions) has a valid ``_builtin_hasattr``.

    This fixes processes where ``com3dx.py`` was loaded more than once before
    pycatia3dx got involved.
    """
    original = _original_hasattr()
    current = builtins.hasattr
    seen: set[int] = set()
    while getattr(current, "__name__", "") == _COM3DX_HASATTR_NAME and id(current) not in seen:
        seen.add(id(current))
        func_globals = getattr(current, "__globals__", None)
        if func_globals is None:
            break
        if func_globals.get("_builtin_hasattr") is None:
            func_globals["_builtin_hasattr"] = original
        current = func_globals["_builtin_hasattr"]


# Heal builtins.hasattr immediately at import time in case external code loaded
# com3dx.py multiple times before pycatia3dx was imported.
_repair_patched_hasattr()

import psutil  # noqa: E402
from win32com.client import Dispatch  # noqa: E402

from pycatia3dx.interfaces.application import Application  # noqa: E402


def _get_com3dx_path() -> pathlib.Path:
    """
    Locate the `com3dx.py` module from the running 3DEXPERIENCE process.

    Returns:
        pathlib.Path: Absolute path to the `com3dx.py` module.

    Raises:
        RuntimeError: If `3DEXPERIENCE.exe` is not currently running.
        FileNotFoundError: If `com3dx.py` does not exist at the derived
            installation path.
    """
    candidates: list[pathlib.Path] = []
    process_found = False

    for proc in psutil.process_iter(['name', 'exe']):
        try:
            name = proc.info['name'] or ''
            if name.lower() != '3dexperience.exe':
                continue
            process_found = True
            exe_location = proc.info['exe']
            if not exe_location:
                continue
            candidates.append(
                pathlib.Path(exe_location)
                .parent
                .parent
                .joinpath("python3dx", "lib", "com3dx.py")
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not process_found:
        raise RuntimeError(
            "3DEXPERIENCE.exe is not running. Please launch the application first."
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Could not find com3dx.py at the expected location(s): "
        + ", ".join(str(c) for c in candidates)
    )


def _import_com3dx_module() -> ModuleType:
    """
    Dynamically import the Dassault Systèmes `com3dx` module using importlib.

    The module is executed only once per Python process and registered in
    ``sys.modules``. Before it is executed, the module namespace is seeded with
    a valid ``_builtin_hasattr`` so that ``com3dx.py`` can never end up with an
    undefined reference, whatever the state of ``builtins.hasattr``. No change
    to the 3DEXPERIENCE installation is required.

    Returns:
        ModuleType: The loaded `com3dx` module.

    Raises:
        ImportError: If the module specification or loader cannot be
            created or executed.
    """
    _repair_patched_hasattr()

    existing = sys.modules.get(_COM3DX_MODULE_NAME)
    if existing is not None and _pure_python_hasattr(existing, "get3dxClient"):
        return existing

    module_path = _get_com3dx_path()
    spec = importlib.util.spec_from_file_location(_COM3DX_MODULE_NAME, module_path)

    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec from {module_path}")

    com3dx = importlib.util.module_from_spec(spec)
    # Seed the global used by com3dx.dbcHasattr. com3dx.py overwrites it with
    # builtins.hasattr when that has not been patched yet, which is the same
    # function, so behaviour is unchanged in the normal case.
    com3dx.__dict__["_builtin_hasattr"] = _original_hasattr()

    lib_dir = str(module_path.parent)
    added_sys_path = False
    if lib_dir not in sys.path:
        sys.path.append(lib_dir)
        added_sys_path = True

    sys.modules[_COM3DX_MODULE_NAME] = com3dx
    try:
        spec.loader.exec_module(com3dx)
    except BaseException:
        sys.modules.pop(_COM3DX_MODULE_NAME, None)
        raise
    finally:
        if added_sys_path and lib_dir in sys.path:
            sys.path.remove(lib_dir)
        _repair_patched_hasattr()

    return com3dx


def catia_application() -> Application:
    """
    Connects to the active 3DEXPERIENCE session and returns a pycatia3dx
    Application object.

    This function tries to dynamically locate and import the `com3dx` module
    provided by the Dassault Systèmes 3DEXPERIENCE installation. The
    module is typically located at:

        3DX_INSTALL_DIR/win_b64/code/python3dx/lib/com3dx.py

    A running instance of `3DEXPERIENCE.exe` is required in order to identify
    the correct installation path.

    If com3dx cannot be used pycatia3dx will fall back to using
    win32com.client.Dispatch. This should only be necessary if the 3DEXPERIENCE
    installation does not include the com3dx.py file.

    Calling this function several times is safe; the com3dx module is only
    loaded once.

    Usage:

    >>> from pycatia3dx import catia3dx
    >>> application = catia3dx()

    :return: Application
    """

    def check_catia_version(application: Application) -> bool:
        if application.name != "3DEXPERIENCE":
            return False
        return True

    try:
        app = Application(_import_com3dx_module().get3dxClient())
    except RuntimeError:
        # 3DEXPERIENCE.exe is not running. Don't fall back to Dispatch as that
        # could silently start or attach to a different CATIA product.
        raise
    except Exception as com3dx_error:
        logger.warning(
            f'Could not connect through com3dx ({type(com3dx_error).__name__}: {com3dx_error}). '
            f'Falling back to win32com.client.Dispatch.'
        )
        try:
            app = Application(Dispatch('CATIA.Application'))
        except Exception as dispatch_error:
            raise com3dx_error from dispatch_error

    if not check_catia_version(app):
        app.logger.warning(f'You are not running CATIA 3DEXPERIENCE. Running "{app.name}".')
    return app
