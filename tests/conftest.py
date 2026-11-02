"""
pytest configuration.

The test data (3DPart, 3DShape, Drawing) is created automatically at the start
of the session if it does not exist yet, see tests/check_test_files.py.
3DEXPERIENCE must be running. Documents that are already open are left alone
and the UI language does not matter.

Environment variables:

    PYCATIA3DX_SKIP_TEST_FILE_SETUP=1   don't check / create the test data.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pycatia3dx import catia3dx
from tests.plm_helpers import close_windows_not_in
from tests.plm_helpers import open_plm_entity
from tests.plm_helpers import window_names

application = catia3dx()

# Windows that were open before the tests started (welcome page, documents the
# user is working on...). They are identified by what is open, not by their
# (localised) names, and are never closed by the test suite.
_initial_windows = window_names(application)


def close_all():
    """
    Close, without saving, every window opened by the test suite.
    """
    close_windows_not_in(application, _initial_windows)


@pytest.fixture(scope="session", autouse=True)
def test_session():
    if not os.environ.get("PYCATIA3DX_SKIP_TEST_FILE_SETUP"):
        from tests.check_test_files import ensure_test_files
        ensure_test_files(application)

    yield  # runs the tests

    close_all()


@pytest.fixture
def file_open(file_name: str, base_type: str):
    open_plm_entity(application, file_name, base_type)
