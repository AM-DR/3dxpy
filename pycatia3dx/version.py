"""
The pycatia3dx version.

Resolved in this order so that it works whatever the current working directory
is and whether pycatia3dx is installed (pip) or used from a source checkout:

1. pyproject.toml next to the package (source checkout / editable install).
2. The installed distribution metadata.
"""
import tomllib
from importlib import metadata
from pathlib import Path


def _read_version() -> str:
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject_path.is_file():
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)
        project = config.get("project", {})
        if project.get("name") == "pycatia3dx" and project.get("version"):
            return project["version"]

    try:
        return metadata.version("pycatia3dx")
    except metadata.PackageNotFoundError:
        return "0.0.0"


version = _read_version()
