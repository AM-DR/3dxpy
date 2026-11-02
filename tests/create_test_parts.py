from __future__ import annotations

from pycatia3dx import CatConstraintMode, CatConstraintType
from pycatia3dx.interfaces.application import Application
from pycatia3dx.interfaces.editor import Editor
from pycatia3dx.mmr_automation_interfaces.part import Part
from pycatia3dx.mode.reference import Reference
from pycatia3dx.plm_session_builder.plm_propagate_service import PLMPropagateService
from pycatia3dx.scripts.vba import vba_nothing
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService
from tests.test_part_parameters import TEST_3DPART_ONE
from tests.test_part_parameters import geom_set_arcs
from tests.test_part_parameters import geom_set_cylinders
from tests.test_part_parameters import geom_set_lines
from tests.test_part_parameters import geom_set_planes
from tests.test_part_parameters import geom_set_points
from tests.test_part_parameters import geom_set_sketches
from tests.test_part_parameters import geom_set_spheres
from tests.test_part_parameters import geom_set_splines
from tests.test_part_parameters import geom_set_surfaces

ALL_GEOM_SETS = (
    geom_set_arcs,
    geom_set_cylinders,
    geom_set_lines,
    geom_set_planes,
    geom_set_points,
    geom_set_sketches,
    geom_set_spheres,
    geom_set_splines,
    geom_set_surfaces,
)


def extract_part_from_editor(editor: Editor) -> Part:
    """
    Return the :class:`Part` from either a standalone ``3DShape`` editor or a
    ``3DPart`` / ``VPMReference`` editor.
    """
    active_com = editor.active_com_object
    if active_com is not None and hasattr(active_com, "MainBody"):
        return Part(active_com)

    plm_product_service: PLMProductService = editor.get_service('PLMProductService')
    root_occurrence = plm_product_service.root_occurrence
    vpm_reference = root_occurrence.reference_root_occurrence_of
    vpm_rep_instance = vpm_reference.rep_instances[0]
    return vpm_rep_instance.reference_instance_of.get_item('Part')


def is_part_populated(part: Part) -> bool:
    hb_names = {hb.name for hb in part.hybrid_bodies}
    return all(expected in hb_names for expected in ALL_GEOM_SETS)


def populate_part(application: Application, part: Part) -> bool:
    """
    Populate ``part`` with the standard test geometry if not already present.

    Returns ``True`` if geometry was created, ``False`` if it was already
    populated.
    """
    if is_part_populated(part):
        application.logger.info(f'"{part.name}" is already populated.')
        return False

    application.logger.info(f'Populating 3DShape "{part.name}".')

    sf = part.shape_factory
    hsf = part.hybrid_shape_factory
    hbs = part.hybrid_bodies
    parms = part.parameters
    main_body = part.main_body

    # Reuse any default empty Geometrical Set created automatically by CATIA
    # user preferences (e.g. "Geometrical Set.1" / "Set géométrique.1") so that
    # the first hybrid body in the part is always `geom_set_arcs`.
    existing_empty = [
        hb for hb in hbs
        if hb.hybrid_shapes.count == 0
        and hb.hybrid_sketches.count == 0
        and hb.hybrid_bodies.count == 0
    ]

    def _next_hb(name: str):
        hb = existing_empty.pop(0) if existing_empty else hbs.add()
        hb.name = name
        return hb

    # ########################### #
    # Create the Geometrical Sets #
    # ########################### #

    hb_geom_set_arcs = _next_hb(geom_set_arcs)
    hb_geom_set_cylinders = _next_hb(geom_set_cylinders)
    hb_geom_set_lines = _next_hb(geom_set_lines)
    hb_geom_set_planes = _next_hb(geom_set_planes)
    hb_geom_set_points = _next_hb(geom_set_points)
    hb_geom_set_sketches = _next_hb(geom_set_sketches)
    hb_geom_set_spheres = _next_hb(geom_set_spheres)
    hb_geom_set_splines = _next_hb(geom_set_splines)
    hb_geom_set_surfaces = _next_hb(geom_set_surfaces)

    # ################# #
    # create parameters #
    # ################# #

    pad_width = 100
    pad_height = 100
    pad_depth = 50

    parms.create_boolean("Activate", True)
    dim_pad_width = parms.create_dimension("pad_width", "LENGTH", pad_width)
    dim_pad_height = parms.create_dimension("pad_height", "LENGTH", pad_height)
    parms.create_dimension("pad_depth", "LENGTH", pad_depth)

    # ################ #
    # create 3D points #
    # ################ #

    point_1 = hsf.add_new_point_coord(0, 0, 0)
    point_2 = hsf.add_new_point_coord(pad_width, 0, 0)
    point_3 = hsf.add_new_point_coord(pad_width, pad_height, 0)
    point_4 = hsf.add_new_point_coord(0, pad_height, 0)

    hb_geom_set_points.append_hybrid_shape(point_1)
    hb_geom_set_points.append_hybrid_shape(point_2)
    hb_geom_set_points.append_hybrid_shape(point_3)
    hb_geom_set_points.append_hybrid_shape(point_4)

    part.update()

    # ################ #
    # create relations #
    # ################ #

    relations = part.relations
    # the dim name here would typically be 'Part1\dim_width'. the com interfaces does not expect the 'Part1' part.
    w_parts = dim_pad_width.name.split("\\")
    h_parts = dim_pad_height.name.split("\\")
    p_w_name = "\\".join(w_parts[1:]) if len(w_parts) > 1 else dim_pad_width.name
    p_h_name = "\\".join(h_parts[1:]) if len(h_parts) > 1 else dim_pad_height.name
    relations.create_formula("formula_1", "", point_2.x, p_w_name)
    relations.create_formula("formula_2", "", point_3.x, p_w_name)
    relations.create_formula("formula_3", "", point_3.y, p_h_name)
    relations.create_formula("formula_5", "", point_4.y, p_h_name)

    # #############################
    # create the sketch for the pad
    # #############################
    xy_plane = part.origin_elements.plane_xy
    ref_xy_plane = Reference(xy_plane.com_object)
    sketch = hb_geom_set_sketches.hybrid_sketches.add(ref_xy_plane)
    factory_2d = sketch.open_edition()
    constraints = sketch.constraints

    point_1_2d = factory_2d.create_point(0, 0)
    point_2_2d = factory_2d.create_point(pad_width, 0)
    point_3_2d = factory_2d.create_point(pad_width, pad_height)
    point_4_2d = factory_2d.create_point(0, pad_height)
    point_1_2d.report_name = 1
    point_2_2d.report_name = 1
    point_3_2d.report_name = 1
    point_4_2d.report_name = 1

    line_1_2d = factory_2d.create_line(0, 0, pad_width, 0)
    line_2_2d = factory_2d.create_line(pad_width, 0, pad_width, pad_height)
    line_3_2d = factory_2d.create_line(pad_width, pad_height, 0, pad_height)
    line_4_2d = factory_2d.create_line(0, pad_height, 0, 0)

    line_1_2d.start_point, line_1_2d.end_point = point_1_2d, point_2_2d
    line_2_2d.start_point, line_2_2d.end_point = point_2_2d, point_3_2d
    line_3_2d.start_point, line_3_2d.end_point = point_3_2d, point_4_2d
    line_4_2d.start_point, line_4_2d.end_point = point_4_2d, point_1_2d

    con_line_1_start = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_1_2d.start_point.com_object),
        point_1,
    )
    con_line_1_start.mode = CatConstraintMode.catCstModeDrivingDimension
    con_line_1_end = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_1_2d.end_point.com_object),
        point_2,
    )
    con_line_1_end.mode = CatConstraintMode.catCstModeDrivingDimension

    con_line_2_start = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_2_2d.start_point.com_object),
        point_2,
    )
    con_line_2_start.mode = CatConstraintMode.catCstModeDrivingDimension
    con_line_2_end = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_2_2d.end_point.com_object),
        point_3,
    )
    con_line_2_end.mode = CatConstraintMode.catCstModeDrivingDimension

    con_line_3_start = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_3_2d.start_point.com_object),
        point_3,
    )
    con_line_3_start.mode = CatConstraintMode.catCstModeDrivingDimension
    con_line_3_end = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_3_2d.end_point.com_object),
        point_4,
    )
    con_line_3_end.mode = CatConstraintMode.catCstModeDrivingDimension

    con_line_4_start = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_4_2d.start_point.com_object),
        point_4,
    )
    con_line_4_start.mode = CatConstraintMode.catCstModeDrivingDimension
    con_line_4_end = constraints.add_bi_elt_cst(
        CatConstraintType.catCstTypeOn,
        Reference(line_4_2d.end_point.com_object),
        point_1,
    )
    con_line_4_end.mode = CatConstraintMode.catCstModeDrivingDimension

    sketch.close_edition()

    # ########## #
    # create pad #
    # ########## #

    part.in_work_object = main_body
    sf.add_new_pad(sketch, pad_depth)

    # ############ #
    # create lines #
    # ############ #

    line_1 = hsf.add_new_line_pt_pt(point_1, point_3)
    line_1.name = "Line.1"
    hb_geom_set_lines.append_hybrid_shape(line_1)

    line_2 = hsf.add_new_line_pt_pt(point_1, point_4)
    line_2.name = "Line.2"
    hb_geom_set_lines.append_hybrid_shape(line_2)

    direction = hsf.add_new_direction(ref_xy_plane)

    line_3 = hsf.add_new_line_pt_dir(
        point_1,
        direction,
        -100,
        100,
        True
    )
    line_3.name = "Line.3"
    hb_geom_set_lines.append_hybrid_shape(line_3)

    # ###################################### #
    # create a surface by filling the sketch #
    # ###################################### #
    fill = hsf.add_new_fill()
    sketch_reference = part.create_reference_from_object(sketch)
    fill.add_bound(sketch_reference)
    hb_geom_set_surfaces.append_hybrid_shape(fill)

    # ############## #
    # create circle  #
    # ############## #
    circle = hsf.add_new_circle_ctr_rad(point_4, ref_xy_plane, True, 25)
    hb_geom_set_arcs.append_hybrid_shape(circle)

    # ########### #
    # create axis #
    # ########### #
    axis_systems = part.axis_systems
    axis = axis_systems[0] if axis_systems.count > 0 else axis_systems.add()
    axis.name = "Axis.1"

    # ############### #
    # create a spline #
    # ############### #
    point_5 = hsf.add_new_point_coord(-54, 47, 0)
    point_6 = hsf.add_new_point_coord(-70, 108, 0)
    point_7 = hsf.add_new_point_coord(-54, 155, 0)
    point_8 = hsf.add_new_point_coord(-70, 200, 0)

    hb_geom_set_points.append_hybrid_shape(point_5)
    hb_geom_set_points.append_hybrid_shape(point_6)
    hb_geom_set_points.append_hybrid_shape(point_7)
    hb_geom_set_points.append_hybrid_shape(point_8)

    spline = hsf.add_new_spline()
    spline.add_point(Reference(point_5.com_object))
    spline.add_point(Reference(point_6.com_object))
    spline.add_point(Reference(point_7.com_object))
    spline.add_point(Reference(point_8.com_object))

    hb_geom_set_splines.append_hybrid_shape(spline)

    # ############# #
    # create planes #
    # ############# #
    plane_offset = hsf.add_new_plane_offset(ref_xy_plane, 200, True)
    plane_offset.name = "Plane.Offset"
    hb_geom_set_planes.append_hybrid_shape(plane_offset)

    ref_line_1 = part.create_reference_from_object(line_1)
    ref_line_2 = part.create_reference_from_object(line_2)
    plane_two_lines = hsf.add_new_plane2_lines(
        ref_line_1,
        ref_line_2
    )
    plane_two_lines.name = "Plane.TwoLines"
    hb_geom_set_planes.append_hybrid_shape(plane_two_lines)

    # ############### #
    # create cylinder #
    # ############### #
    direction = hsf.add_new_direction(ref_xy_plane)
    cylinder = hsf.add_new_cylinder(point_3, 33, 100, 0, direction)
    hb_geom_set_cylinders.append_hybrid_shape(cylinder)

    # ############# #
    # create sphere #
    # ############# #
    sphere = hsf.add_new_sphere(
        point_3,
        vba_nothing,
        100.0,
        -90.0,
        90.0,
        0.0,
        360.0
    )
    hb_geom_set_spheres.append_hybrid_shape(sphere)

    part.update()
    return True


def create_part_geometry(
    application: Application,
    save: bool = True,
    close: bool = True,
) -> bool:
    """
    Populate the active ``3DPart`` or ``3DShape`` editor with test geometry,
    optionally saving to PLM and closing the active window.
    """
    editor = application.active_editor
    part = extract_part_from_editor(editor)
    populated = populate_part(application, part)

    if populated and save:
        plm_propagate_service: PLMPropagateService = application.get_session_service('PLMPropagateService')
        plm_propagate_service.plm_propagate()

    if close and populated:
        application.active_window.close()
        application.logger.info(f'Created "{TEST_3DPART_ONE}".')

    return populated
