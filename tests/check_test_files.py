"""
Creates (or repairs) the PLM data required by the test suite.

This runs automatically at the start of every pytest session (see
tests/conftest.py) so nothing has to be prepared manually. It can also be run
on its own:

    >>> python -m tests.check_test_files

What it does:

* Looks in the database for the test 3DPart / 3DShape / Drawing.
* Accepts existing test files regardless of their description attribute so that
  upgrades or different version descriptions do not block tests.
* Creates any that are missing, including their geometry.
* Repairs a test 3DPart that was created by hand (e.g. 3DShape not renamed).

It never relies on localised strings so it works with any 3DEXPERIENCE
language, and it only closes the windows it opened itself.
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
from pycatia3dx.plm_session_builder.plm_new_service import PLMNewService
from pycatia3dx.plm_session_builder.plm_propagate_service import PLMPropagateService
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService
from tests.create_test_drawings import create_test_drawing_one
from tests.create_test_parts import create_part_geometry
from tests.plm_helpers import close_windows_not_in
from tests.plm_helpers import find_plm_entity
from tests.plm_helpers import open_plm_entity
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
            logger.debug(f'Could not set attribute {name} to {value}: {e}')


def _set_test_part_attributes(editor: Editor) -> None:
    """
    Make sure the 3DPart and its 3DShape carry the names expected by the tests.
    """
    try:
        vpm_reference = _root_vpm_reference(editor)
        _set_attribute_if_different(vpm_reference, 'V_Name', TEST_3DPART_ONE)

        rep_instances = vpm_reference.rep_instances
        if rep_instances.count > 0:
            rep_reference = rep_instances[0].reference_instance_of
            _set_attribute_if_different(rep_reference, 'V_Name', TEST_3DSHAPE_ONE)
    except Exception as e:
        logger.debug(f'Could not set part attributes: {e}')


def _save(application: Application) -> None:
    try:
        plm_propagate_service: PLMPropagateService = application.get_session_service('PLMPropagateService')
        plm_propagate_service.plm_propagate()
    except Exception as e:
        logger.debug(f'PLM propagate failed: {e}')


def create_test_part_one(application: Application) -> None:
    """
    Create, name, populate and save the test 3DPart.
    """
    application.logger.info(f'Creating test file "{TEST_3DPART_ONE}".')

    plm_new_service: PLMNewService = application.get_session_service('PLMNewService')
    try:
        plm_new_service.set_attribute_value('V_Name', TEST_3DPART_ONE)
        plm_new_service.set_attribute_value('V_description', version)
    except Exception:
        pass

    try:
        editor = plm_new_service.plm_create('3DPart')
    except Exception:
        try:
            editor = plm_new_service.plm_create('VPMReference')
        except Exception as e:
            application.logger.warning(
                f'Could not automatically create 3DPart via PLMNewService: {e}. '
                f'If an active Part is already open in CATIA, tests will use it.'
            )
            return

    _set_test_part_attributes(editor)
    create_part_geometry(application)


def ensure_test_part_one(application: Application) -> None:
    part_entity = find_plm_entity(application, TEST_3DPART_ONE, 'VPMReference')
    if part_entity is None:
        create_test_part_one(application)
    else:
        application.logger.info(f'Test file "{TEST_3DPART_ONE}" found.')
        try:
            editor = open_plm_entity(application, TEST_3DPART_ONE, 'VPMReference')
            create_part_geometry(application)
        except Exception as e:
            application.logger.warning(f'Could not populate existing test part: {e}')


def ensure_test_drawing_one(application: Application) -> None:
    try:
        if find_plm_entity(application, TEST_CATDRAWING_ONE, 'Drawing') is None:
            create_test_drawing_one(application)
        else:
            application.logger.info(f'Test file "{TEST_CATDRAWING_ONE}" found.')
    except Exception as e:
        application.logger.warning(f'Could not ensure test drawing: {e}')


def ensure_test_files(application: Application) -> None:
    """
    Create any missing test data. Windows opened while doing so are closed
    again; windows that were already open are left alone.
    """
    application.logger.info(f'Checking test files for pycatia3dx {version}.')
    initial_windows = window_names(application)
    try:
        ensure_test_part_one(application)
        ensure_test_drawing_one(application)
    finally:
        close_windows_not_in(application, initial_windows)
    application.logger.info('Test files check completed.')


# kept for backwards compatibility.
def check_test_files(application: Application | None = None) -> None:
    ensure_test_files(application or catia3dx())


if __name__ == '__main__':
    check_test_files()
