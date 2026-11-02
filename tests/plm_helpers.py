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
from pycatia3dx.plm_access.search_service import SearchService
from pycatia3dx.plm_modeller_base.plm_entity import PLMEntity

logger = logging.getLogger(__name__)


def find_plm_entity(app: Application, title: str, base_type: str,
                    description: str | None = None) -> PLMEntity | None:
    """
    Search the database for a PLM entity named `title` of type `base_type`.

    If `description` is given and a matching entity has that description, it is
    preferred. Otherwise, any entity with matching `V_Name` is returned so that
    users do not need to manually change descriptions across versions.

    :param app:
    :param title: value of V_Name.
    :param base_type: 'VPMReference', '3DShape', 'Drawing', ...
    :param description: preferred V_description or None.
    :return: the matching PLMEntity or None.
    """
    search: SearchService = app.get_session_service('Search')
    db_search = search.database_search
    db_search.base_type = base_type
    db_search.all_minor_versions = True
    db_search.add_easy_criteria('V_Name', title)
    try:
        search.search()
    except Exception as e:
        logger.warning(f"Search failed for {title} ({base_type}): {e}")
        return None

    results = list(db_search.results)
    if not results:
        return None

    if description is not None:
        for plm_entity in results:
            try:
                if plm_entity.get_attribute_value('V_description') == description:
                    return plm_entity
            except Exception:
                pass

    return results[0]


def open_plm_entity(app: Application, title: str, base_type: str) -> Editor:
    """
    Open the test PLM entity `title` and return its editor.
    If it is already open its window is activated.

    base_type = 'VPMReference', '3DShape', '3DPart' or 'Drawing'

    :param app:
    :param title:
    :param str base_type:
    """
    # 1. First check if the target is already active
    try:
        active_win = app.active_window
        if active_win and (title in active_win.name or active_win.name in title):
            return app.active_editor
    except Exception:
        pass

    # 2. Check all open windows for the title
    for window in app.windows:
        try:
            if title in window.name or window.name in title:
                window.activate()
                return app.active_editor
        except Exception:
            continue

    # 3. If looking for 3DShape, check if the 3DPart window is open
    from tests.test_part_parameters import TEST_3DPART_ONE, TEST_3DSHAPE_ONE
    if title == TEST_3DSHAPE_ONE:
        for window in app.windows:
            try:
                if TEST_3DPART_ONE in window.name or "3DPart" in window.name:
                    window.activate()
                    return app.active_editor
            except Exception:
                continue

    # 4. Search in database
    plm_entity = find_plm_entity(app, title, base_type)

    # 5. If 3DShape wasn't found as a standalone root entity, search for parent 3DPart
    if plm_entity is None and base_type == '3DShape':
        plm_entity = find_plm_entity(app, TEST_3DPART_ONE, 'VPMReference')

    # 6. If found in database, open it
    if plm_entity is not None:
        plm_open_service = app.get_session_service('PLMOpenService')
        plm_open_service.plm_open(plm_entity)
        return app.active_editor

    # 7. Fallback: if there is any active editor open, use it
    try:
        editor = app.active_editor
        if editor and editor.name:
            logger.warning(
                f'Could not find PLM entity "{title}" ({base_type}) in database, '
                f'falling back to currently active editor "{editor.name}".'
            )
            return editor
    except Exception:
        pass

    raise CATIAApplicationException(
        f'Test file "{title}" ({base_type}) was not found in database and no active editor is open.'
    )


def window_names(app: Application) -> set[str]:
    """
    Names of all the currently open windows. Used to remember which windows
    existed before the tests started (welcome page, user documents, ...),
    whatever their (localised) names are.
    """
    try:
        return {window.name for window in app.windows}
    except Exception:
        return set()


def close_windows_not_in(app: Application, keep: set[str]) -> None:
    """
    Close every window whose name is not in `keep` without saving.

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
