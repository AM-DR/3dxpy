"""
Pure-Python Abaqus ``.inp`` Input Deck Builder, Parser, & Parametric Editor.

Enables creating complete Abaqus finite-element models from scratch in Python or
loading/modifying ``.inp`` decks exported from CATIA 3DEXPERIENCE FEM / Mechanical
Scenario Creation without requiring an Abaqus/CAE license.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


@dataclass
class InpKeywordBlock:
    """Represents a single ``*KEYWORD, PARAM=VAL`` block and its data lines."""

    keyword: str
    parameters: dict[str, str | None] = field(default_factory=dict)
    data_lines: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    def format_header(self) -> str:
        parts = [f"*{self.keyword}"]
        for key, val in self.parameters.items():
            if val is None or val == "":
                parts.append(key)
            else:
                parts.append(f"{key}={val}")
        return ", ".join(parts)

    def to_inp_lines(self) -> list[str]:
        out: list[str] = []
        for comment in self.comments:
            out.append(comment if comment.startswith("**") else f"** {comment}")
        out.append(self.format_header())
        out.extend(self.data_lines)
        return out


def _format_num(val: int | float | str) -> str:
    if isinstance(val, int) and not isinstance(val, bool):
        return str(val)
    if isinstance(val, float):
        return f"{val:.10g}"
    return str(val)


def _chunk_csv_lines(items: Sequence[int | float | str], per_line: int = 16) -> list[str]:
    lines: list[str] = []
    for idx in range(0, len(items), per_line):
        chunk = items[idx : idx + per_line]
        lines.append(", ".join(_format_num(x) for x in chunk))
    return lines


class AbaqusInpDeck:
    """
    Structured Abaqus ``.inp`` input deck reader, editor, and builder.

    Example::

        deck = AbaqusInpDeck(heading="3D Cantilever")
        deck.add_nodes({1: (0, 0, 0), 2: (100, 0, 0), 3: (100, 10, 0), 4: (0, 10, 0)})
        deck.add_elements("CPS4R", {1: (1, 2, 3, 4)}, elset="ALL_ELS")
        deck.add_nset("FIXED", [1, 4])
        deck.add_nset("TIP", [2, 3])
        deck.add_isotropic_material("STEEL", youngs_modulus=210000.0, poissons_ratio=0.3, density=7.85e-9)
        deck.add_solid_section("ALL_ELS", "STEEL", thickness=5.0)
        deck.add_static_step(
            name="TipLoad",
            nlgeom=False,
            boundaries=[("FIXED", 1, 2, 0.0)],
            cloads=[("TIP", 2, -500.0)],
            node_outputs=["U", "RF"],
            element_outputs=["S", "PEEQ"],
        )
        deck.write("cantilever.inp")
    """

    def __init__(self, heading: str | None = None, blocks: list[InpKeywordBlock] | None = None):
        self.blocks: list[InpKeywordBlock] = list(blocks) if blocks is not None else []
        if heading is not None and not self.find_blocks("HEADING"):
            self.blocks.insert(0, InpKeywordBlock("HEADING", data_lines=[heading]))

    # ------------------------------------------------------------------
    # Parsing & serialization
    # ------------------------------------------------------------------
    @classmethod
    def from_text(cls, text: str) -> AbaqusInpDeck:
        """Parse an Abaqus ``.inp`` deck string into keyword blocks."""
        blocks: list[InpKeywordBlock] = []
        pending_comments: list[str] = []
        current_block: InpKeywordBlock | None = None

        raw_lines = text.splitlines()
        idx = 0
        while idx < len(raw_lines):
            line = raw_lines[idx].rstrip("\r\n")
            stripped = line.strip()

            if not stripped:
                idx += 1
                continue

            if stripped.startswith("**"):
                pending_comments.append(stripped)
                idx += 1
                continue

            if stripped.startswith("*"):
                # Handle line continuation on keyword header lines ending with ','
                header = stripped[1:]
                while header.rstrip().endswith(",") and idx + 1 < len(raw_lines):
                    idx += 1
                    nxt = raw_lines[idx].strip()
                    if nxt.startswith("**"):
                        pending_comments.append(nxt)
                        continue
                    header = header + " " + nxt

                tokens = [t.strip() for t in header.split(",") if t.strip()]
                kw_name = tokens[0].upper() if tokens else "UNKNOWN"
                params: dict[str, str | None] = {}
                for tok in tokens[1:]:
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        params[k.strip().upper()] = v.strip()
                    else:
                        params[tok.strip().upper()] = None

                current_block = InpKeywordBlock(
                    keyword=kw_name,
                    parameters=params,
                    data_lines=[],
                    comments=pending_comments,
                )
                pending_comments = []
                blocks.append(current_block)
            else:
                if current_block is None:
                    current_block = InpKeywordBlock(keyword="HEADING", comments=pending_comments)
                    pending_comments = []
                    blocks.append(current_block)
                if pending_comments:
                    for c in pending_comments:
                        current_block.data_lines.append(c)
                    pending_comments = []
                current_block.data_lines.append(line)

            idx += 1

        return cls(blocks=blocks)

    @classmethod
    def from_file(cls, path: str | pathlib.Path) -> AbaqusInpDeck:
        """Load and parse an Abaqus ``.inp`` file from disk."""
        return cls.from_text(pathlib.Path(path).read_text(encoding="utf-8", errors="replace"))

    def to_string(self) -> str:
        """Render the complete ``.inp`` deck as text."""
        lines: list[str] = []
        for block in self.blocks:
            lines.extend(block.to_inp_lines())
        return "\n".join(lines) + "\n"

    def write(self, path: str | pathlib.Path) -> pathlib.Path:
        """Write the ``.inp`` deck to ``path`` and return the resolved path."""
        out_path = pathlib.Path(path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.to_string(), encoding="utf-8")
        return out_path

    # ------------------------------------------------------------------
    # Querying & editing keyword blocks
    # ------------------------------------------------------------------
    def find_blocks(self, keyword: str, **param_filters: str) -> list[InpKeywordBlock]:
        """Return all blocks matching ``keyword`` (case-insensitive) and optional parameters."""
        target = keyword.lstrip("*").upper()
        upper_filters = {k.upper(): v.upper() for k, v in param_filters.items()}
        matched: list[InpKeywordBlock] = []
        for blk in self.blocks:
            if blk.keyword.upper() != target:
                continue
            ok = True
            for fk, fv in upper_filters.items():
                actual = blk.parameters.get(fk)
                if actual is None or actual.upper() != fv:
                    ok = False
                    break
            if ok:
                matched.append(blk)
        return matched

    def set_parameters(self, parameters: Mapping[str, int | float | str]) -> AbaqusInpDeck:
        """
        Insert or update a ``*PARAMETER`` keyword block at the top of the deck
        for Abaqus parametric studies (``<param_name>`` syntax).
        """
        data = [f"{name} = {_format_num(val)}" for name, val in parameters.items()]
        existing = self.find_blocks("PARAMETER")
        if existing:
            existing[0].data_lines = data
        else:
            insert_at = 1 if (self.blocks and self.blocks[0].keyword == "HEADING") else 0
            self.blocks.insert(insert_at, InpKeywordBlock("PARAMETER", data_lines=data))
        return self

    def count_nodes(self) -> int:
        """Count total node definitions across all ``*NODE`` blocks."""
        total = 0
        for blk in self.find_blocks("NODE"):
            total += sum(1 for ln in blk.data_lines if ln.strip() and not ln.strip().startswith("**"))
        return total

    def count_elements(self) -> int:
        """Count total element definitions across all ``*ELEMENT`` blocks."""
        total = 0
        for blk in self.find_blocks("ELEMENT"):
            for ln in blk.data_lines:
                s = ln.strip()
                if not s or s.startswith("**"):
                    continue
                # Continuation lines in multi-node elements start after a trailing comma
                total += 1
        return total

    # ------------------------------------------------------------------
    # Mesh & Set Builders
    # ------------------------------------------------------------------
    def add_nodes(
        self,
        nodes: Mapping[int, Sequence[float]] | Iterable[tuple[int, Sequence[float]]],
        *,
        nset: str | None = None,
    ) -> InpKeywordBlock:
        """Add a ``*NODE`` block from ``{node_id: (x, y[, z])}``."""
        items = nodes.items() if isinstance(nodes, Mapping) else nodes
        params: dict[str, str | None] = {}
        if nset:
            params["NSET"] = nset
        lines = [
            ", ".join([str(int(nid)), *(_format_num(c) for c in coords)])
            for nid, coords in items
        ]
        blk = InpKeywordBlock("NODE", parameters=params, data_lines=lines)
        self.blocks.append(blk)
        return blk

    def add_elements(
        self,
        elem_type: str,
        elements: Mapping[int, Sequence[int]] | Iterable[tuple[int, Sequence[int]]],
        *,
        elset: str | None = None,
    ) -> InpKeywordBlock:
        """Add an ``*ELEMENT, TYPE=<elem_type>`` block."""
        items = elements.items() if isinstance(elements, Mapping) else elements
        params: dict[str, str | None] = {"TYPE": elem_type.upper()}
        if elset:
            params["ELSET"] = elset
        lines: list[str] = []
        for eid, conn in items:
            row = [int(eid), *(int(n) for n in conn)]
            if len(row) <= 16:
                lines.append(", ".join(str(x) for x in row))
            else:
                # Abaqus wraps >16 integers across lines with trailing comma
                for start in range(0, len(row), 15):
                    seg = row[start : start + 15]
                    suffix = "," if start + 15 < len(row) else ""
                    lines.append(", ".join(str(x) for x in seg) + suffix)
        blk = InpKeywordBlock("ELEMENT", parameters=params, data_lines=lines)
        self.blocks.append(blk)
        return blk

    def add_nset(
        self,
        name: str,
        ids_or_range: Sequence[int],
        *,
        generate: bool = False,
        instance: str | None = None,
    ) -> InpKeywordBlock:
        """Add an ``*NSET`` node set."""
        params: dict[str, str | None] = {"NSET": name}
        if instance:
            params["INSTANCE"] = instance
        if generate:
            params["GENERATE"] = None
        blk = InpKeywordBlock("NSET", parameters=params, data_lines=_chunk_csv_lines(ids_or_range))
        self.blocks.append(blk)
        return blk

    def add_elset(
        self,
        name: str,
        ids_or_range: Sequence[int],
        *,
        generate: bool = False,
        instance: str | None = None,
    ) -> InpKeywordBlock:
        """Add an ``*ELSET`` element set."""
        params: dict[str, str | None] = {"ELSET": name}
        if instance:
            params["INSTANCE"] = instance
        if generate:
            params["GENERATE"] = None
        blk = InpKeywordBlock("ELSET", parameters=params, data_lines=_chunk_csv_lines(ids_or_range))
        self.blocks.append(blk)
        return blk

    # ------------------------------------------------------------------
    # Material & Section Builders
    # ------------------------------------------------------------------
    def add_isotropic_material(
        self,
        name: str,
        *,
        youngs_modulus: float,
        poissons_ratio: float,
        density: float | None = None,
        plastic_table: Sequence[tuple[float, float]] | None = None,
        expansion_coeff: float | None = None,
        conductivity: float | None = None,
        specific_heat: float | None = None,
    ) -> list[InpKeywordBlock]:
        """Add ``*MATERIAL`` with elastic, optional density, plasticity, and thermal properties."""
        added: list[InpKeywordBlock] = []
        mat = InpKeywordBlock("MATERIAL", parameters={"NAME": name})
        self.blocks.append(mat)
        added.append(mat)

        if density is not None:
            dens = InpKeywordBlock("DENSITY", data_lines=[f"{_format_num(density)},"])
            self.blocks.append(dens)
            added.append(dens)

        elas = InpKeywordBlock(
            "ELASTIC",
            data_lines=[f"{_format_num(youngs_modulus)}, {_format_num(poissons_ratio)}"],
        )
        self.blocks.append(elas)
        added.append(elas)

        if plastic_table:
            plas = InpKeywordBlock(
                "PLASTIC",
                data_lines=[
                    f"{_format_num(stress)}, {_format_num(pstrain)}"
                    for stress, pstrain in plastic_table
                ],
            )
            self.blocks.append(plas)
            added.append(plas)

        if expansion_coeff is not None:
            exp = InpKeywordBlock("EXPANSION", data_lines=[f"{_format_num(expansion_coeff)},"])
            self.blocks.append(exp)
            added.append(exp)

        if conductivity is not None:
            cond = InpKeywordBlock("CONDUCTIVITY", data_lines=[f"{_format_num(conductivity)},"])
            self.blocks.append(cond)
            added.append(cond)

        if specific_heat is not None:
            sh = InpKeywordBlock("SPECIFIC HEAT", data_lines=[f"{_format_num(specific_heat)},"])
            self.blocks.append(sh)
            added.append(sh)

        return added

    def add_solid_section(
        self,
        elset: str,
        material: str,
        *,
        thickness: float | None = None,
        orientation: str | None = None,
    ) -> InpKeywordBlock:
        """Add ``*SOLID SECTION``."""
        params: dict[str, str | None] = {"ELSET": elset, "MATERIAL": material}
        if orientation:
            params["ORIENTATION"] = orientation
        lines = [f"{_format_num(thickness)},"] if thickness is not None else [","]
        blk = InpKeywordBlock("SOLID SECTION", parameters=params, data_lines=lines)
        self.blocks.append(blk)
        return blk

    def add_shell_section(
        self,
        elset: str,
        material: str,
        thickness: float,
        *,
        section_points: int = 5,
    ) -> InpKeywordBlock:
        """Add ``*SHELL SECTION``."""
        blk = InpKeywordBlock(
            "SHELL SECTION",
            parameters={"ELSET": elset, "MATERIAL": material},
            data_lines=[f"{_format_num(thickness)}, {int(section_points)}"],
        )
        self.blocks.append(blk)
        return blk

    # ------------------------------------------------------------------
    # Step, Load, Boundary, & Output Builders
    # ------------------------------------------------------------------
    def add_static_step(
        self,
        name: str = "Step-1",
        *,
        nlgeom: bool = False,
        inc: int = 100,
        time_incrementation: tuple[float, float, float, float] = (1.0, 1.0, 1e-5, 1.0),
        boundaries: Sequence[tuple[str | int, int | str, int | None, float | None]] = (),
        cloads: Sequence[tuple[str | int, int, float]] = (),
        dloads: Sequence[tuple[str, str, float]] = (),
        node_outputs: Sequence[str] = ("U", "RF"),
        element_outputs: Sequence[str] = ("S", "E", "PEEQ"),
    ) -> list[InpKeywordBlock]:
        """Add a complete ``*STEP`` .. ``*STATIC`` .. ``*END STEP`` sequence."""
        added: list[InpKeywordBlock] = []
        step_params: dict[str, str | None] = {
            "NAME": name,
            "NLGEOM": "YES" if nlgeom else "NO",
            "INC": str(int(inc)),
        }
        step_blk = InpKeywordBlock("STEP", parameters=step_params)
        self.blocks.append(step_blk)
        added.append(step_blk)

        static_blk = InpKeywordBlock(
            "STATIC",
            data_lines=[", ".join(_format_num(v) for v in time_incrementation)],
        )
        self.blocks.append(static_blk)
        added.append(static_blk)

        if boundaries:
            bc_lines: list[str] = []
            for target, dof1, dof2, mag in boundaries:
                if isinstance(dof1, str):
                    bc_lines.append(f"{target}, {dof1}")
                elif dof2 is None and mag is None:
                    bc_lines.append(f"{target}, {dof1}")
                elif mag is None:
                    bc_lines.append(f"{target}, {dof1}, {dof2}")
                else:
                    end_dof = dof1 if dof2 is None else dof2
                    bc_lines.append(f"{target}, {dof1}, {end_dof}, {_format_num(mag)}")
            bc_blk = InpKeywordBlock("BOUNDARY", data_lines=bc_lines)
            self.blocks.append(bc_blk)
            added.append(bc_blk)

        if cloads:
            cl_blk = InpKeywordBlock(
                "CLOAD",
                data_lines=[f"{target}, {int(dof)}, {_format_num(val)}" for target, dof, val in cloads],
            )
            self.blocks.append(cl_blk)
            added.append(cl_blk)

        if dloads:
            dl_blk = InpKeywordBlock(
                "DLOAD",
                data_lines=[f"{elset}, {load_type}, {_format_num(mag)}" for elset, load_type, mag in dloads],
            )
            self.blocks.append(dl_blk)
            added.append(dl_blk)

        if node_outputs or element_outputs:
            out_blk = InpKeywordBlock("OUTPUT", parameters={"FIELD": None, "VARIABLE": "PRESELECT"})
            self.blocks.append(out_blk)
            added.append(out_blk)
            if node_outputs:
                no_blk = InpKeywordBlock("NODE OUTPUT", data_lines=[", ".join(node_outputs)])
                self.blocks.append(no_blk)
                added.append(no_blk)
            if element_outputs:
                eo_blk = InpKeywordBlock("ELEMENT OUTPUT", data_lines=[", ".join(element_outputs)])
                self.blocks.append(eo_blk)
                added.append(eo_blk)

        end_blk = InpKeywordBlock("END STEP")
        self.blocks.append(end_blk)
        added.append(end_blk)
        return added

    def add_frequency_step(
        self,
        name: str = "Modal",
        *,
        num_eigenvalues: int = 10,
        min_freq: float | None = None,
        max_freq: float | None = None,
        boundaries: Sequence[tuple[str | int, int | str, int | None, float | None]] = (),
    ) -> list[InpKeywordBlock]:
        """Add a ``*STEP`` .. ``*FREQUENCY`` (Lanczos modal analysis) .. ``*END STEP`` sequence."""
        added: list[InpKeywordBlock] = []
        step_blk = InpKeywordBlock("STEP", parameters={"NAME": name, "PERTURBATION": None})
        self.blocks.append(step_blk)
        added.append(step_blk)

        min_s = _format_num(min_freq) if min_freq is not None else ""
        max_s = _format_num(max_freq) if max_freq is not None else ""
        freq_blk = InpKeywordBlock(
            "FREQUENCY",
            parameters={"EIGENSOLVER": "LANCZOS"},
            data_lines=[f"{int(num_eigenvalues)}, {min_s}, {max_s}"],
        )
        self.blocks.append(freq_blk)
        added.append(freq_blk)

        if boundaries:
            bc_lines = []
            for target, dof1, dof2, _ in boundaries:
                if isinstance(dof1, str):
                    bc_lines.append(f"{target}, {dof1}")
                else:
                    bc_lines.append(f"{target}, {dof1}, {dof1 if dof2 is None else dof2}")
            bc_blk = InpKeywordBlock("BOUNDARY", data_lines=bc_lines)
            self.blocks.append(bc_blk)
            added.append(bc_blk)

        end_blk = InpKeywordBlock("END STEP")
        self.blocks.append(end_blk)
        added.append(end_blk)
        return added
