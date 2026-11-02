"""
Creates (or repairs) the PLM data required by the test suite.

This runs automatically at the start of every pytest session (see
tests/conftest.py) so nothing has to be prepared manually. It can also be run
standalone:

    >>> python .\\tests\\check_test_files.py

What it does:

* Looks in the database for the test 3DShape / 3DPart / Drawing.
* Reuses existing test files regardless of their ``V_description`` value so
  nobody has to edit descriptions or recreate files manually.
* Automatically creates and populates missing test data — via ``3DPart`` when
  permitted by the license, or directly via standalone ``3DShape`` otherwise.
* Records post-save ``V_Name`` aliases so enterprise autonaming rules on
  3DEXPERIENCE Cloud never break test lookups.
* Works in every 3DEXPERIENCE UI language and leaves windows that were already
  open untouched.
"""
from __future__ import annotations

import logging
import os
import sys

if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pycatia3dx import catia3dx
from pycatia3dx import version
from pycatia3dx.interfaces.application import Application
from pycatia3dx.interfaces.editor import Editor
from pycatia3dx.mmr_automation_interfaces.part import Part
from pycatia3dx.plm_session_builder.plm_new_service import PLMNewService
from pycatia3dx.plm_session_builder.plm_propagate_service import PLMPropagateService
from pycatia3dx.product_structure_client.vpm_rep_reference import VPMRepReference
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService
from tests.create_test_drawings import create_test_drawing_one
from tests.create_test_parts import extract_part_from_editor
from tests.create_test_parts import populate_part
from tests.plm_helpers import close_windows_not_in
from tests.plm_helpers import find_plm_entity
from tests.plm_helpers import register_entity_alias
from tests.plm_helpers import window_names
from tests.test_part_parameters import TEST_3DPART_ONE
from tests.test_part_parameters import TEST_3DSHAPE_ONE
from tests.test_part_parameters import TEST_CATDRAWING_ONE

logger = logging.getLogger(__name__)


def _root_vpm_reference(editor: Editor):
    plm_product_service: PLMProductService = editor.get_service('PLMProductService')
    return plm_product_service.root_occurrence.reference_root_occurrence_of


def _set_attribute_if_different(plm_entity, name: str, value: str) -> None:
    try:
        current = plm_entity.get_attribute_value(name)
    except Exception:
        current = None
    if current != value:
        try:
            plm_entity.set_attribute_value(name, value)
        except Exception as e:
            logger.debug(f'Could not set attribute {name} to "{value}": {e}')


def _set_test_part_attributes(editor: Editor) -> None:
    """
    Attempt to set the canonical test names and description on a ``3DPart`` and
    its child ``3DShape``. If enterprise Business Logic Rules keep auto-named
    values, ``_record_part_and_shape_aliases`` captures the actual names.
    """
    try:
        vpm_reference = _root_vpm_reference(editor)
        _set_attribute_if_different(vpm_reference, 'V_Name', TEST_3DPART_ONE)
        _set_attribute_if_different(vpm_reference, 'V_description', version)

        rep_instances = vpm_reference.rep_instances
        if rep_instances.count > 0:
            rep_reference = rep_instances[0].reference_instance_of
            _set_attribute_if_different(rep_reference, 'V_Name', TEST_3DSHAPE_ONE)
            _set_attribute_if_different(rep_reference, 'V_description', version)
    except Exception as e:
        logger.debug(f'Could not set 3DPart attributes: {e}')


def _record_part_and_shape_aliases(editor: Editor) -> None:
    """
    Read the actual ``V_Name`` values after propagation and register aliases in
    case enterprise autonaming overrode the requested names.
    """
    try:
        vpm_reference = _root_vpm_reference(editor)
        actual_part_name = vpm_reference.get_attribute_value('V_Name')
        if isinstance(actual_part_name, str):
            register_entity_alias(TEST_3DPART_ONE, 'VPMReference', actual_part_name)

        rep_instances = vpm_reference.rep_instances
        if rep_instances.count > 0:
            rep_reference = rep_instances[0].reference_instance_of
            actual_shape_name = rep_reference.get_attribute_value('V_Name')
            if isinstance(actual_shape_name, str):
                register_entity_alias(TEST_3DSHAPE_ONE, '3DShape', actual_shape_name)
    except Exception as e:
        logger.debug(f'Could not read back 3DPart/3DShape names: {e}')


def _save(application: Application) -> bool:
    try:
        plm_propagate_service: PLMPropagateService = application.get_session_service('PLMPropagateService')
        plm_propagate_service.plm_propagate()
        return True
    except Exception as e:
        logger.warning(f'PLM propagate did not succeed: {e}')
        return False


def _create_via_3dpart(application: Application) -> bool:
    plm_new_service: PLMNewService = application.get_session_service('PLMNewService')
    try:
        plm_new_service.set_attribute_value('V_Name', TEST_3DPART_ONE)
        plm_new_service.set_attribute_value('V_description', version)
    except Exception:
        pass

    editor = plm_new_service.plm_create('3DPart')
    _set_test_part_attributes(editor)
    part = extract_part_from_editor(editor)
    populate_part(application, part)
    saved = _save(application)
    _record_part_and_shape_aliases(editor)
    return saved


def _create_via_3dshape(application: Application) -> bool:
    application.logger.info(f'Creating standalone test 3DShape "{TEST_3DSHAPE_ONE}".')
    plm_new_service: PLMNewService = application.get_session_service('PLMNewService')
    try:
        plm_new_service.set_attribute_value('V_Name', TEST_3DSHAPE_ONE)
        plm_new_service.set_attribute_value('V_description', version)
    except Exception:
        pass

    editor = plm_new_service.plm_create('3DShape')
    part = Part(editor.active_com_object)

    rep_reference: VPMRepReference | None = None
    try:
        rep_reference = VPMRepReference(part.com_object.Parent)
        _set_attribute_if_different(rep_reference, 'V_Name', TEST_3DSHAPE_ONE)
        _set_attribute_if_different(rep_reference, 'V_description', version)
    except Exception as e:
        logger.debug(f'Could not set standalone 3DShape attributes: {e}')

    populate_part(application, part)
    saved = _save(application)

    actual_name: str | None = None
    if rep_reference is not None:
        try:
            val = rep_reference.get_attribute_value('V_Name')
            if isinstance(val, str) and val:
                actual_name = val
        except Exception:
            pass
    if not actual_name:
        try:
            actual_name = application.active_window.name
        except Exception:
            pass
    if actual_name:
        register_entity_alias(TEST_3DSHAPE_ONE, '3DShape', actual_name)

    return saved


def create_test_part_one(application: Application) -> bool:
    """
    Create, populate and save the test geometry, preferring ``3DPart`` when
    supported by the license and falling back to standalone ``3DShape``.
    """
    application.logger.info(f'Creating test geometry "{TEST_3DSHAPE_ONE}".')
    before = window_names(application)
    try:
        return _create_via_3dpart(application)
    except Exception as e:
        logger.info(f'3DPart creation unavailable ({e}); falling back to standalone 3DShape.')
        close_windows_not_in(application, before)
        return _create_via_3dshape(application)


def ensure_test_part_one(application: Application) -> bool:
    """
    Ensure the populated test ``3DShape`` exists. Returns ``True`` if it is
    persisted in the database, or ``False`` if kept open in-memory only.
    """
    plm_open_service = application.get_session_service('PLMOpenService')

    # 1. Check if TEST_3DSHAPE_ONE already exists directly in PLM.
    shape_entity = find_plm_entity(application, TEST_3DSHAPE_ONE, '3DShape')
    if shape_entity is not None:
        application.logger.info(f'Test file "{TEST_3DSHAPE_ONE}" found.')
        plm_open_service.plm_open(shape_entity)
        part = extract_part_from_editor(application.active_editor)
        if populate_part(application, part):
            return _save(application)
        return True

    # 2. Check if TEST_3DPART_ONE exists (e.g. created manually with default
    #    3DShape name or older description).
    part_entity = find_plm_entity(application, TEST_3DPART_ONE, 'VPMReference')
    if part_entity is not None:
        application.logger.info(f'Test file "{TEST_3DPART_ONE}" found.')
        plm_open_service.plm_open(part_entity)
        editor = application.active_editor
        _set_test_part_attributes(editor)
        part = extract_part_from_editor(editor)
        populate_part(application, part)
        _save(application)
        _record_part_and_shape_aliases(editor)
        return True

    # 3. Nothing exists yet — create and populate automatically.
    return create_test_part_one(application)


def ensure_test_drawing_one(application: Application) -> None:
    try:
        if find_plm_entity(application, TEST_CATDRAWING_ONE, 'Drawing') is not None:
            application.logger.info(f'Test file "{TEST_CATDRAWING_ONE}" found.')
            return
        if find_plm_entity(application, TEST_3DPART_ONE, 'VPMReference') is None:
            return
        create_test_drawing_one(application)
    except Exception as e:
        application.logger.warning(f'Skipping optional test drawing creation: {e}')


def ensure_test_files(application: Application) -> None:
    """
    Create or repair any missing test data. Windows opened during setup are
    closed afterwards (unless saving to PLM was disallowed, in which case the
    in-memory test shape stays open for the test session); windows that were
    already open before setup are always left untouched.
    """
    application.logger.info(f'Checking test files for pycatia3dx {version}.')
    initial_windows = window_names(application)
    persisted = True
    try:
        persisted = ensure_test_part_one(application)
        if persisted:
            ensure_test_drawing_one(application)
    finally:
        if persisted:
            close_windows_not_in(application, initial_windows)
    application.logger.info('Test files ready.')


# kept for backwards compatibility.
def check_test_files(application: Application | None = None) -> None:
    ensure_test_files(application or catia3dx())


if __name__ == '__main__':
    check_test_files()
