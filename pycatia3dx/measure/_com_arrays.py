"""
Helpers for COM methods whose sole parameter is an output ``CATSafeArrayVariant``
(for example ``GetAxisSystemFromMeasure``).

CATIA's ``IDispatch`` implementation rejects Python ``win32com`` SAFEARRAY
parameters with ``DISP_E_TYPEMISMATCH`` ("Type mismatch"). Consistent with
``MeasurableAxisSystem.get_axis``, ``MeasureBetween.get_components`` and the
other array-returning methods in pycatia3dx, we evaluate a tiny ``CATVBScript``
helper through ``SystemService.Evaluate`` so CATIA receives a native VBScript
Variant array. ``On Error Resume Next`` ensures that unset optional results
(such as a measure with no associated axis system) cleanly return ``None``
instead of raising a COM error.
"""
from __future__ import annotations

from typing import Any

from pycatia3dx import CATScriptLanguage


def call_array_out_method(target: Any, method_name: str, size: int) -> tuple | None:
    """
    Invoke ``method_name`` on ``target`` (an ``AnyObject`` wrapper or raw COM
    object) with a VBScript Variant array of ``size`` elements and return the
    populated tuple, or ``None`` if no values were produced.
    """
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")

    if hasattr(target, "application") and hasattr(target, "com_object"):
        application = target.application
        com_object = target.com_object
    else:
        from pycatia3dx.interfaces.application import Application
        com_object = target
        application = Application(com_object.Application)

    upper = size - 1
    vba_function_name = "pycatia3dx_get_array_out"
    vba_code = f"""
    Public Function {vba_function_name}(target_obj)
        On Error Resume Next
        Dim out_arr ({upper})
        target_obj.{method_name} out_arr
        If Err.Number <> 0 Then
            {vba_function_name} = Null
        Else
            {vba_function_name} = out_arr
        End If
    End Function
    """

    result = application.system_service.evaluate(
        vba_code,
        CATScriptLanguage.CATVBScriptLanguage,
        vba_function_name,
        [com_object],
    )

    if isinstance(result, (list, tuple)):
        if all(item is None for item in result):
            return None
        return tuple(result)
    return None
