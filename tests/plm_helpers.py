"""
Helpers used by the test suite to find, open and close PLM entities.

None of these helpers rely on localised strings (window captions such as the
3DEXPERIENCE "Welcome Page", default feature names such as "PartBody", ...)
so the test suite runs on any 3DEXPERIENCE language and without requiring
specific descriptions or manual file manipulation.
"""
from __future__ import annotations

import logging

from pycatia3dx import version
from pycatia3dx.exceptions import CATIAApplicationException
from pycatia3dx.interfaces.application import Application
from pycatia3dx.interfaces.editor import Editor
from pycatia3dx.mmr_automation_interfaces.part import Part
from pycatia3dx.plm_access.search_service import SearchService
from pycatia3dx.plm_modeller_base.plm_entity import PLMEntity
from pycatia3dx.plm_session_builder.plm_new_service import PLMNewService
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService

logger = logging.getLogger(__name__)

# Maps (requested_title, base_type) -> actual V_Name in PLM when enterprise
# autonaming rules or pre-existing unrenamed representations use another name.
_ENTITY_ALIASES: dict[tuple[str, str], str] = {}


def register_entity_alias(requested_title: str, base_type: str, actual_title: str) -> None:
    if actual_title and actual_title != requested_title:
        _ENTITY_ALIASES[(requested_title, base_type)] = actual_title


def resolve_entity_title(title: str, base_type: str) -> str:
    return _ENTITY_ALIASES.get((title, base_type), title)


def is_part_editor(editor: Editor | None) -> bool:
    """
    Return ``True`` when ``editor`` is an active ``3DShape`` editor whose
    active object is a :class:`Part` (as opposed to the Welcome Page, a
    ``VPMReference`` product editor, or a ``Drawing`` editor).
    """
    if editor is None:
        return False
    try:
        com_obj = editor.active_com_object
        return com_obj is not None and hasattr(com_obj, "MainBody")
    except Exception:
        return False


def _editor_matches_base_type(editor: Editor | None, base_type: str) -> bool:
    if editor is None:
        return False
    if base_type == "3DShape":
        return is_part_editor(editor)
    return True


def _window_matches_title(window_name: str, target_title: str) -> bool:
    if not window_name or not target_title:
        return False
    return window_name == target_title or window_name.startswith(target_title + " ")


def find_plm_entity(
    app: Application,
    title: str,
    base_type: str,
    description: str | None = None,
) -> PLMEntity | None:
    """
    Search the database for a PLM entity named ``title`` of type ``base_type``.

    If multiple entities match ``V_Name``, one matching ``description`` (or the
    current ``pycatia3dx`` version) is preferred; otherwise the first match is
    returned regardless of its description so users never have to edit
    ``V_description`` manually.
    """
    candidates = [resolve_entity_title(title, base_type)]
    if title not in candidates:
        candidates.append(title)

    preferred_desc = description if description is not None else version

    for candidate in candidates:
        if not candidate:
            continue
        search: SearchService = app.get_session_service('Search')
        db_search = search.database_search
        db_search.base_type = base_type
        db_search.all_minor_versions = True
        db_search.add_easy_criteria('V_Name', candidate)
        try:
            search.search()
        except Exception as e:
            logger.warning(f'Search failed for "{candidate}" ({base_type}): {e}')
            continue

        results = list(db_search.results)
        if not results:
            continue

        if preferred_desc:
            for plm_entity in results:
                try:
                    if plm_entity.get_attribute_value('V_description') == preferred_desc:
                        return plm_entity
                except Exception:
                    continue

        return results[0]

    return None


def _discover_shape_in_test_part(app: Application) -> PLMEntity | None:
    """
    If ``TEST_3DPART_ONE`` exists in the database with an unrenamed child
    ``3DShape``, discover that child's real ``V_Name``, register its alias, and
    return its ``3DShape`` :class:`PLMEntity`.
    """
    from tests.test_part_parameters import TEST_3DPART_ONE, TEST_3DSHAPE_ONE

    part_entity = find_plm_entity(app, TEST_3DPART_ONE, 'VPMReference')
    if part_entity is None:
        return None

    before = window_names(app)
    actual_shape_name: str | None = None
    try:
        plm_open_service = app.get_session_service('PLMOpenService')
        plm_open_service.plm_open(part_entity)
        editor = app.active_editor
        plm_product_service: PLMProductService = editor.get_service('PLMProductService')
        vpm_ref = plm_product_service.root_occurrence.reference_root_occurrence_of
        if vpm_ref.rep_instances.count > 0:
            rep_ref = vpm_ref.rep_instances[0].reference_instance_of
            actual_shape_name = rep_ref.get_attribute_value('V_Name')
    except Exception as e:
        logger.debug(f'Could not inspect child 3DShape of "{TEST_3DPART_ONE}": {e}')
    finally:
        close_windows_not_in(app, before)

    if actual_shape_name:
        register_entity_alias(TEST_3DSHAPE_ONE, '3DShape', actual_shape_name)
        return find_plm_entity(app, actual_shape_name, '3DShape')
    return None


def _create_in_memory_test_shape(app: Application, requested_title: str) -> Editor:
    """
    Last-resort fallback when PLM database save/search is unavailable: create
    and populate a fresh ``3DShape`` directly in the session without touching
    any of the user's open documents.
    """
    from tests.create_test_parts import populate_part

    plm_new_service: PLMNewService = app.get_session_service('PLMNewService')
    try:
        plm_new_service.set_attribute_value('V_Name', requested_title)
        plm_new_service.set_attribute_value('V_description', version)
    except Exception:
        pass

    editor = plm_new_service.plm_create('3DShape')
    part = Part(editor.active_com_object)
    populate_part(app, part)
    try:
        register_entity_alias(requested_title, '3DShape', app.active_window.name)
    except Exception:
        pass
    return editor


def open_plm_entity(app: Application, title: str, base_type: str) -> Editor:
    """
    Open the test PLM entity ``title`` of ``base_type`` and return its editor.
    If a matching window is already open, it is activated and reused.
    """
    from tests.test_part_parameters import TEST_3DSHAPE_ONE

    candidates = [resolve_entity_title(title, base_type)]
    if title not in candidates:
        candidates.append(title)

    # 1. Check active window first.
    try:
        active_win = app.active_window
        if active_win and any(_window_matches_title(active_win.name, c) for c in candidates):
            editor = app.active_editor
            if _editor_matches_base_type(editor, base_type):
                return editor
    except Exception:
        pass

    # 2. Check all open windows.
    try:
        open_windows = list(app.windows)
    except Exception:
        open_windows = []

    for window in open_windows:
        try:
            if any(_window_matches_title(window.name, c) for c in candidates):
                window.activate()
                editor = app.active_editor
                if _editor_matches_base_type(editor, base_type):
                    return editor
        except Exception:
            continue

    # 3. Search in the PLM database.
    plm_entity = find_plm_entity(app, title, base_type)

    # 4. If looking for TEST_3DSHAPE_ONE, check if it lives inside TEST_3DPART_ONE
    #    under an auto-generated or localised representation name.
    if plm_entity is None and base_type == '3DShape' and title == TEST_3DSHAPE_ONE:
        plm_entity = _discover_shape_in_test_part(app)

    # 5. Open from database if found.
    if plm_entity is not None:
        plm_open_service = app.get_session_service('PLMOpenService')
        plm_open_service.plm_open(plm_entity)
        return app.active_editor

    # 6. Self-healing fallback for 3DShape tests when database storage is
    #    unavailable (e.g. read-only space or skipped file setup).
    if base_type == '3DShape' and title == TEST_3DSHAPE_ONE:
        logger.warning(
            f'"{title}" was not found in database; creating an in-memory test 3DShape.'
        )
        return _create_in_memory_test_shape(app, title)

    raise CATIAApplicationException(
        f'Test file "{title}" ({base_type}) was not found in the database.'
    )


def window_names(app: Application) -> set[str]:
    """
    Names of all currently open windows. Used to remember which windows existed
    before the tests started (welcome page, user documents, ...), whatever
    their localised captions are.
    """
    try:
        return {window.name for window in app.windows}
    except Exception:
        return set()


def close_windows_not_in(app: Application, keep: set[str]) -> None:
    """
    Close every window whose name is not in ``keep`` without saving.

    Only windows opened by the test suite are closed, so documents the user
    had open before running the tests (and the welcome page, whatever it is
    called in the current language) are left untouched.
    """
    try:
        windows = list(app.windows)
    except Exception:
        return

    to_close = [window for window in windows if window.name not in keep]
    if not to_close:
        return

    try:
        app.display_file_alerts = False
    except Exception:
        pass

    try:
        for window in to_close:
            try:
                window.close()
            except Exception as e:
                app.logger.debug(f'Could not close window: {e}')
    finally:
        try:
            app.display_file_alerts = True
        except Exception:
            pass
