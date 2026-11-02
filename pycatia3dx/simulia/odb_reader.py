"""
Abaqus ``.odb`` Output Database Reader Bridge.

Extracts steps, frames, field outputs (stress ``S``, displacement ``U``,
equivalent plastic strain ``PEEQ``, reaction forces ``RF``, temperature ``NT11``),
and history outputs from Abaqus ``.odb`` files into pure Python dictionaries and
CSV tables by running a built-in ``odbAccess`` script inside ``abaqus python``.
"""
from __future__ import annotations

import csv
import pathlib
from typing import Any

from pycatia3dx.simulia.abaqus import AbaqusRunner

_INSPECT_ODB_SCRIPT = """
from odbAccess import openOdb

odb = openOdb(path=PAYLOAD['odb_path'], readOnly=bool(PAYLOAD.get('read_only', True)))
try:
    steps_info = {}
    for step_name, step_obj in odb.steps.items():
        frames = []
        field_keys = []
        for idx, frame in enumerate(step_obj.frames):
            frames.append({
                'index': idx,
                'increment_number': getattr(frame, 'incrementNumber', idx),
                'frame_value': float(frame.frameValue),
                'description': str(frame.description),
            })
            if idx == len(step_obj.frames) - 1:
                field_keys = list(frame.fieldOutputs.keys())
        hist_regions = {}
        for reg_name, reg_obj in step_obj.historyRegions.items():
            hist_regions[reg_name] = list(reg_obj.historyOutputs.keys())
        steps_info[step_name] = {
            'number': int(step_obj.number),
            'procedure': str(step_obj.procedure),
            'total_time': float(step_obj.totalTime),
            'num_frames': len(frames),
            'frames': frames,
            'field_outputs': field_keys,
            'history_regions': hist_regions,
        }

    RESULT = {
        'path': PAYLOAD['odb_path'],
        'instances': list(odb.rootAssembly.instances.keys()),
        'node_sets': list(odb.rootAssembly.nodeSets.keys()),
        'element_sets': list(odb.rootAssembly.elementSets.keys()),
        'steps': steps_info,
    }
finally:
    odb.close()
"""

_FIELD_OUTPUT_SCRIPT = """
from odbAccess import openOdb

odb = openOdb(path=PAYLOAD['odb_path'], readOnly=bool(PAYLOAD.get('read_only', True)))
try:
    step_name = PAYLOAD.get('step')
    if not step_name:
        step_name = list(odb.steps.keys())[-1]
    step_obj = odb.steps[step_name]
    frame_idx = int(PAYLOAD.get('frame', -1))
    frame_obj = step_obj.frames[frame_idx]
    var_name = PAYLOAD['variable']
    field = frame_obj.fieldOutputs[var_name]

    inst_name = PAYLOAD.get('instance')
    nset_name = PAYLOAD.get('node_set')
    elset_name = PAYLOAD.get('element_set')

    root = odb.rootAssembly
    target_container = root.instances[inst_name] if inst_name else root
    if nset_name:
        field = field.getSubset(region=target_container.nodeSets[nset_name])
    if elset_name:
        field = field.getSubset(region=target_container.elementSets[elset_name])

    max_vals = PAYLOAD.get('max_values')
    records = []
    max_mises = None
    max_mag = None

    for idx, val in enumerate(field.values):
        mises_v = getattr(val, 'mises', None)
        mag_v = getattr(val, 'magnitude', None)
        if mises_v is not None:
            mises_v = float(mises_v)
            if max_mises is None or mises_v > max_mises:
                max_mises = mises_v
        if mag_v is not None:
            mag_v = float(mag_v)
            if max_mag is None or mag_v > max_mag:
                max_mag = mag_v

        if max_vals is not None and idx >= int(max_vals):
            continue

        raw_data = getattr(val, 'dataDouble', None)
        if raw_data is None:
            raw_data = getattr(val, 'data', None)
        if raw_data is not None:
            try:
                data_out = [float(x) for x in raw_data]
            except TypeError:
                data_out = [float(raw_data)]
        else:
            data_out = []

        inst_obj = getattr(val, 'instance', None)
        records.append({
            'instance': inst_obj.name if inst_obj is not None else None,
            'node_label': int(val.nodeLabel) if getattr(val, 'nodeLabel', None) else None,
            'element_label': int(val.elementLabel) if getattr(val, 'elementLabel', None) else None,
            'integration_point': int(val.integrationPoint) if getattr(val, 'integrationPoint', None) else None,
            'data': data_out,
            'mises': mises_v,
            'magnitude': mag_v,
        })

    RESULT = {
        'step': step_name,
        'frame': frame_idx,
        'frame_value': float(frame_obj.frameValue),
        'variable': var_name,
        'component_labels': [str(c) for c in getattr(field, 'componentLabels', ())],
        'total_count': len(field.values),
        'max_mises': max_mises,
        'max_magnitude': max_mag,
        'values': records,
    }
finally:
    odb.close()
"""

_HISTORY_OUTPUT_SCRIPT = """
from odbAccess import openOdb

odb = openOdb(path=PAYLOAD['odb_path'], readOnly=bool(PAYLOAD.get('read_only', True)))
try:
    step_name = PAYLOAD.get('step')
    if not step_name:
        step_name = list(odb.steps.keys())[-1]
    step_obj = odb.steps[step_name]

    reg_name = PAYLOAD.get('region')
    if not reg_name:
        reg_name = list(step_obj.historyRegions.keys())[0]
    reg_obj = step_obj.historyRegions[reg_name]

    var_name = PAYLOAD['variable']
    hist_obj = reg_obj.historyOutputs[var_name]
    RESULT = {
        'step': step_name,
        'region': reg_name,
        'variable': var_name,
        'description': str(getattr(hist_obj, 'description', '')),
        'data': [{'time': float(t), 'value': float(v)} for t, v in hist_obj.data],
    }
finally:
    odb.close()
"""


class AbaqusOdbReader:
    """
    High-level Python reader for Abaqus ``.odb`` result files.

    Uses ``abaqus python`` via :class:`~pycatia3dx.simulia.abaqus.AbaqusRunner`
    so callers on Python 3.11–3.14 can query ``.odb`` files directly without
    manual script files.
    """

    def __init__(
        self,
        odb_path: str | pathlib.Path,
        *,
        runner: AbaqusRunner | None = None,
        read_only: bool = True,
    ):
        self.odb_path = pathlib.Path(odb_path).resolve()
        self.runner = runner or AbaqusRunner()
        self.read_only = read_only

    def inspect(self) -> dict[str, Any]:
        """Return steps, frames, available field/history variables, instances, and sets."""
        res = self.runner.execute_inline(
            _INSPECT_ODB_SCRIPT,
            {"odb_path": str(self.odb_path), "read_only": self.read_only},
            mode="python",
        )
        if res.output_data is None:
            raise RuntimeError(f"Failed to inspect ODB {self.odb_path}: {res.stderr or res.stdout}")
        return dict(res.output_data)

    def read_field_output(
        self,
        variable: str,
        *,
        step: str | None = None,
        frame: int = -1,
        instance: str | None = None,
        node_set: str | None = None,
        element_set: str | None = None,
        max_values: int | None = None,
    ) -> dict[str, Any]:
        """Extract field output values (e.g. ``'S'``, ``'U'``, ``'PEEQ'``, ``'RF'``)."""
        res = self.runner.execute_inline(
            _FIELD_OUTPUT_SCRIPT,
            {
                "odb_path": str(self.odb_path),
                "read_only": self.read_only,
                "variable": variable,
                "step": step,
                "frame": frame,
                "instance": instance,
                "node_set": node_set,
                "element_set": element_set,
                "max_values": max_values,
            },
            mode="python",
        )
        if res.output_data is None:
            raise RuntimeError(
                f"Failed to read field output {variable!r} from {self.odb_path}: {res.stderr or res.stdout}"
            )
        return dict(res.output_data)

    def read_history_output(
        self,
        variable: str,
        *,
        step: str | None = None,
        region: str | None = None,
    ) -> dict[str, Any]:
        """Extract time-history output curve ``[{'time': t, 'value': v}, ...]``."""
        res = self.runner.execute_inline(
            _HISTORY_OUTPUT_SCRIPT,
            {
                "odb_path": str(self.odb_path),
                "read_only": self.read_only,
                "variable": variable,
                "step": step,
                "region": region,
            },
            mode="python",
        )
        if res.output_data is None:
            raise RuntimeError(
                f"Failed to read history output {variable!r} from {self.odb_path}: {res.stderr or res.stdout}"
            )
        return dict(res.output_data)

    def export_field_to_csv(
        self,
        csv_path: str | pathlib.Path,
        variable: str,
        *,
        step: str | None = None,
        frame: int = -1,
        instance: str | None = None,
        node_set: str | None = None,
        element_set: str | None = None,
    ) -> pathlib.Path:
        """Extract a field output and export all values to a CSV file."""
        data = self.read_field_output(
            variable,
            step=step,
            frame=frame,
            instance=instance,
            node_set=node_set,
            element_set=element_set,
        )
        out = pathlib.Path(csv_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        comp_labels: list[str] = data.get("component_labels") or []

        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            headers = [
                "instance",
                "node_label",
                "element_label",
                "integration_point",
                "mises",
                "magnitude",
                *(comp_labels if comp_labels else ["v0", "v1", "v2", "v3", "v4", "v5"]),
            ]
            writer.writerow(headers)
            for row in data.get("values", []):
                vals = row.get("data", [])
                writer.writerow([
                    row.get("instance") or "",
                    row.get("node_label") or "",
                    row.get("element_label") or "",
                    row.get("integration_point") or "",
                    row.get("mises") if row.get("mises") is not None else "",
                    row.get("magnitude") if row.get("magnitude") is not None else "",
                    *vals,
                ])
        return out
