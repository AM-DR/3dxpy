"""
Helpers for COM methods that return their result through a
``CATSafeArrayVariant`` output parameter (e.g. ``GetAxisSystemFromMeasure``).

Python can't pass a VB array "by reference" directly. Calling such a method
without an argument raises ``DISP_E_TYPEMISMATCH`` / ``DISP_E_PARAMNOTOPTIONAL``
with late-bound COM, which is what pycatia3dx gets through com3dx. These
helpers pass a pre-sized by-reference VARIANT array instead and read the
result back.
"""
from __future__ import annotations

from typing import Any

try:
    import pythoncom
    from win32com.client import VARIANT
except ImportError:
    pythoncom = None
    VARIANT = None


def call_array_out_method(com_object: Any, method_name: str, size: int) -> tuple | None:
    """
    Call `method_name` on `com_object` whose only parameter is an output
    array of `size` elements and return that array as a tuple.

    Several argument types are tried in turn because different 3DEXPERIENCE
    releases / COM bridges accept different ones.

    :param com_object: the COM object.
    :param str method_name: the COM method name, e.g. 'GetAxisSystemFromMeasure'.
    :param int size: number of elements of the output array.
    :return: tuple or None if the method didn't return anything.
    """
    method = getattr(com_object, method_name)
    last_error: Exception | None = None

    if pythoncom is not None and VARIANT is not None:
        for vt in (pythoncom.VT_VARIANT, pythoncom.VT_R8):
            try:
                out = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | vt, [0.0] * size)
                result = method(out)
                value = out.value if out.value is not None else result
                if value is not None:
                    return _to_tuple(value)
            except Exception as e:
                last_error = e
                continue

    # Try passing a mutable list as out param
    try:
        arr = [0.0] * size
        res = method(arr)
        if any(x != 0.0 for x in arr):
            return tuple(arr)
        if res is not None:
            return _to_tuple(res)
    except Exception as e:
        last_error = e

    # early-bound / type-library aware dispatch returns out parameters directly.
    try:
        return _to_tuple(method())
    except Exception as e:
        if last_error:
            raise last_error
        raise e


def _to_tuple(value: Any) -> tuple | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)
