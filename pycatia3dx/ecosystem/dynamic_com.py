"""
Dynamic COM proxy & universal service wrappers for 3DEXPERIENCE.

Allows Python code to call *any* COM object, Session Service, or Editor Service
across CATIA, SIMULIA, DELMIA, ENOVIA, BIOVIA, GEOVIA, and 3DEXCITE — even when
a static wrapper class has not been generated — with automatic ``snake_case``
to ``PascalCase`` (including Dassault acronym prefixes like ``PLM``, ``SIM``,
``SMA``, ``CAT``, ``DEL``, ``DNB``, ``OLP``, ``VPM``) resolution and automatic
wrapping/unwrapping of ``AnyObject`` instances.
"""
from __future__ import annotations

from typing import Any

from pycatia3dx.interfaces.service import Service
from pycatia3dx.system.any_object import AnyObject

_PRIMITIVE_TYPES = (str, bytes, bool, int, float)

# Common Dassault Systèmes uppercase acronym prefixes used in Automation IDL.
_DS_ACRONYMS: dict[str, tuple[str, ...]] = {
    "plm": ("PLM", "Plm"),
    "sim": ("Sim", "SIM"),
    "sma": ("SMA", "Sma"),
    "cat": ("CAT", "Cat"),
    "del": ("DEL", "Del"),
    "dnb": ("DNB", "Dnb"),
    "olp": ("OLP", "Olp"),
    "vpm": ("VPM", "Vpm"),
    "mat": ("MAT", "Mat"),
    "pcb": ("PCB", "Pcb"),
    "fcb": ("FCB", "Fcb"),
    "val": ("VAL", "Val"),
    "srs": ("SRS", "Srs"),
    "rfg": ("RFG", "Rfg"),
    "str": ("Str", "STR"),
    "kin": ("Kin", "KIN"),
    "id": ("ID", "Id"),
    "3d": ("3D",),
    "2d": ("2D",),
}


def snake_to_com_candidates(name: str) -> list[str]:
    """
    Generate ordered COM member-name candidates from a Python identifier.

    Examples:
        ``"plm_create"`` -> ``["plm_create", "PlmCreate", "PLMCreate", "plmCreate"]``
        ``"get_product_root_occurrence"`` -> ``["get_product_root_occurrence", "GetProductRootOccurrence", ...]``
    """
    if not name:
        return []

    candidates: list[str] = []

    def _add(val: str) -> None:
        if val and val not in candidates:
            candidates.append(val)

    _add(name)

    if "_" not in name:
        if name[0].islower():
            _add(name[0].upper() + name[1:])
        upper = name.upper()
        if name.lower() in _DS_ACRONYMS:
            for acr in _DS_ACRONYMS[name.lower()]:
                _add(acr)
        else:
            _add(upper)
        return candidates

    parts = [p for p in name.split("_") if p]
    if not parts:
        return candidates

    # Standard PascalCase: GetSessionService
    pascal = "".join(p[0].upper() + p[1:] for p in parts)
    _add(pascal)

    # Acronym-aware variants: PLMCreate, SIMDynClashServices, Get3DXClient, etc.
    variant_lists: list[tuple[str, ...]] = []
    for p in parts:
        low = p.lower()
        if low in _DS_ACRONYMS:
            opts = _DS_ACRONYMS[low] + (p[0].upper() + p[1:],)
            dedup = tuple(dict.fromkeys(opts))
            variant_lists.append(dedup)
        else:
            variant_lists.append((p[0].upper() + p[1:],))

    # Build combinations cleanly (bounded to avoid combinatorial explosion)
    combos: list[str] = [""]
    for opts in variant_lists:
        next_combos: list[str] = []
        for prefix in combos[:16]:
            for opt in opts:
                next_combos.append(prefix + opt)
        combos = next_combos
    for combo in combos:
        _add(combo)

    # camelCase fallback
    camel = parts[0].lower() + "".join(p[0].upper() + p[1:] for p in parts[1:])
    _add(camel)

    return candidates


def unwrap_com_arg(value: Any) -> Any:
    """Unwrap ``AnyObject`` (or nested lists/tuples of them) to raw COM objects."""
    if value is None or isinstance(value, _PRIMITIVE_TYPES):
        return value
    if isinstance(value, AnyObject):
        return value.com_object
    if not isinstance(value, type) and hasattr(value, "com_object"):
        return value.com_object
    if isinstance(value, tuple):
        return tuple(unwrap_com_arg(v) for v in value)
    if isinstance(value, list):
        return [unwrap_com_arg(v) for v in value]
    return value


def is_com_dispatch(value: Any) -> bool:
    """Return True if ``value`` looks like a raw COM/IDispatch object."""
    if value is None or isinstance(value, (*_PRIMITIVE_TYPES, dict, set, AnyObject)):
        return False
    if isinstance(value, (tuple, list)):
        return False
    cls = type(value)
    mod = getattr(cls, "__module__", "") or ""
    cls_name = getattr(cls, "__name__", "") or ""
    if "win32com" in mod or "pywintypes" in mod or cls_name in ("CDispatch", "PyIDispatch"):
        return True
    if hasattr(value, "_oleobj_"):
        return True
    return False


def wrap_com_result(value: Any) -> Any:
    """Wrap raw COM dispatch return values into :class:`DynamicCOMObject`."""
    if is_com_dispatch(value):
        return DynamicCOMObject(value)
    if isinstance(value, tuple):
        return tuple(wrap_com_result(v) for v in value)
    if isinstance(value, list):
        return [wrap_com_result(v) for v in value]
    return value


class DynamicCOMObject(AnyObject):
    """
    Universal Python wrapper around any 3DEXPERIENCE ``IDispatch`` COM object.

    Supports:
    - All :class:`~pycatia3dx.system.any_object.AnyObject` properties/methods.
    - Automatic ``snake_case`` -> ``PascalCase`` / acronym COM member dispatch.
    - Automatic unwrapping of ``pycatia3dx`` wrapper arguments to ``.com_object``.
    - Automatic wrapping of returned COM objects into ``DynamicCOMObject``.
    - ``call_vba_array_method(...)`` for methods returning ``CATSafeArrayVariant``
      outputs that Python ``win32com`` late-binding would otherwise reject with
      ``DISP_E_TYPEMISMATCH``.
    """

    _INTERNAL_ATTRS = frozenset({"com_object", "_member_cache", "service_id", "_raw_target"})

    def __init__(self, com_object: Any):
        if isinstance(com_object, AnyObject):
            com_object = com_object.com_object
        object.__setattr__(self, "_member_cache", {})
        object.__setattr__(self, "com_object", com_object)
        super().__init__(com_object)

    def _resolve_com_member_name(self, attr: str) -> str:
        cache: dict[str, str] = object.__getattribute__(self, "_member_cache")
        if attr in cache:
            return cache[attr]

        raw = object.__getattribute__(self, "com_object")
        candidates = snake_to_com_candidates(attr)
        for candidate in candidates:
            try:
                getattr(raw, candidate)
                cache[attr] = candidate
                return candidate
            except AttributeError:
                continue

        # Case-insensitive scan of dir(raw) if type information is available
        lower_target = attr.replace("_", "").lower()
        try:
            available = dir(raw)
        except Exception:
            available = []
        for member in available:
            if member.replace("_", "").lower() == lower_target:
                cache[attr] = member
                return member

        raise AttributeError(
            f"{type(self).__name__} could not find COM member for {attr!r} "
            f"(tried: {', '.join(candidates)})"
        )

    def __getattr__(self, attr: str) -> Any:
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)

        raw = object.__getattribute__(self, "com_object")
        com_name = self._resolve_com_member_name(attr)
        target = getattr(raw, com_name)

        if callable(target):
            def _invoke(*args: Any, **kwargs: Any) -> Any:
                unwrapped_args = tuple(unwrap_com_arg(a) for a in args)
                unwrapped_kwargs = {k: unwrap_com_arg(v) for k, v in kwargs.items()}
                result = target(*unwrapped_args, **unwrapped_kwargs)
                return wrap_com_result(result)

            _invoke.__name__ = attr
            return _invoke

        return wrap_com_result(target)

    def __setattr__(self, attr: str, value: Any) -> None:
        if attr in self._INTERNAL_ATTRS or attr.startswith("_"):
            object.__setattr__(self, attr, value)
            return

        # Check if the attribute is a property descriptor on the wrapper class
        cls_attr = getattr(type(self), attr, None)
        if isinstance(cls_attr, property):
            if cls_attr.fset is None:
                raise AttributeError(f"Property {attr!r} is read-only")
            cls_attr.fset(self, value)
            return

        raw = object.__getattribute__(self, "com_object")
        unwrapped = unwrap_com_arg(value)
        for candidate in snake_to_com_candidates(attr):
            try:
                getattr(raw, candidate)
                setattr(raw, candidate, unwrapped)
                return
            except AttributeError:
                continue
        # Fallback: set using primary PascalCase candidate on dynamic IDispatch
        candidates = snake_to_com_candidates(attr)
        setattr(raw, candidates[1] if len(candidates) > 1 else attr, unwrapped)

    def call_com(self, exact_member_name: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a COM method by its exact case-sensitive Automation IDL name."""
        raw = object.__getattribute__(self, "com_object")
        fn = getattr(raw, exact_member_name)
        unwrapped_args = tuple(unwrap_com_arg(a) for a in args)
        unwrapped_kwargs = {k: unwrap_com_arg(v) for k, v in kwargs.items()}
        return wrap_com_result(fn(*unwrapped_args, **unwrapped_kwargs))

    def call_vba_array_method(
        self,
        method_name: str,
        out_array_size: int,
        *in_args: Any,
    ) -> tuple[Any, ...]:
        """
        Invoke a COM method whose final parameter is an output ``CATSafeArrayVariant``
        of length ``out_array_size`` via ``SystemService.Evaluate`` (VBScript).

        Example::

            coords = dyn_point.call_vba_array_method("GetCoordinates", 3)
        """
        from pycatia3dx import CATScriptLanguage

        if out_array_size <= 0:
            raise ValueError("out_array_size must be >= 1")

        ubound = out_array_size - 1
        in_names = [f"arg{i}" for i in range(len(in_args))]
        sig_params = ", ".join(["targetObj", *in_names])
        call_params = ", ".join([*in_names, "arr"])
        vb_code = (
            f"Function _pycatia_dyn_arr({sig_params})\n"
            f"    On Error Resume Next\n"
            f"    ReDim arr({ubound})\n"
            f"    targetObj.{method_name} {call_params}\n"
            f"    If Err.Number <> 0 Then\n"
            f"        _pycatia_dyn_arr = Empty\n"
            f"    Else\n"
            f"        _pycatia_dyn_arr = arr\n"
            f"    End If\n"
            f"End Function"
        )
        eval_params = [self.com_object, *(unwrap_com_arg(a) for a in in_args)]
        res = self.application.system_service.evaluate(
            vb_code,
            CATScriptLanguage.CATVBScriptLanguage,
            "_pycatia_dyn_arr",
            eval_params,
        )
        if res is None:
            raise RuntimeError(
                f"VBScript evaluation of {method_name!r} failed or returned Empty."
            )
        return tuple(wrap_com_result(v) for v in res)

    def __getitem__(self, key: int | str) -> DynamicCOMObject:
        """Allow indexing COM collections directly via ``obj[1]`` or ``obj['Name']``."""
        raw = object.__getattribute__(self, "com_object")
        return DynamicCOMObject(raw.Item(key))

    def __len__(self) -> int:
        raw = object.__getattribute__(self, "com_object")
        return int(raw.Count)

    def __repr__(self) -> str:
        try:
            obj_name = self.name
        except Exception:
            obj_name = "<COMObject>"
        return f"DynamicCOMObject(name={obj_name!r})"


class DynamicCOMService(DynamicCOMObject, Service):
    """
    Dynamic ``Service`` wrapper returned when requesting any 3DEXPERIENCE
    session service or editor service that does not have a dedicated static class.
    """

    def __init__(self, com_object: Any, service_id: str = ""):
        object.__setattr__(self, "service_id", service_id)
        super().__init__(com_object)

    def __repr__(self) -> str:
        svc = object.__getattribute__(self, "service_id")
        if svc:
            return f"DynamicCOMService(service_id={svc!r})"
        try:
            return f"DynamicCOMService(name={self.name!r})"
        except Exception:
            return "DynamicCOMService()"
