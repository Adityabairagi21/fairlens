"""Low-level JSON and CSV file operations.

Every function converts low-level errors (missing file, bad JSON, no
permission, wrong encoding) into ``DataFileError`` with a message the UI
can show directly.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import IO, Any

import pandas as pd

from modules.exceptions import DataFileError


def load_json(path: Path, default: Any = None) -> Any:
    """Read a JSON file.

    If the file does not exist and ``default`` is given, the default is
    written to disk and returned, so a fresh install starts cleanly.
    """
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        if default is None:
            raise DataFileError(f"Unable to find {path.name}.") from None
        save_json(path, default)
        return default
    except json.JSONDecodeError as error:
        raise DataFileError(
            f"Unable to read {path.name}. The file may be corrupted "
            f"(line {error.lineno}, column {error.colno})."
        ) from error
    except UnicodeDecodeError as error:
        raise DataFileError(f"Unable to read {path.name}. It is not a UTF-8 text file.") from error
    except PermissionError as error:
        raise DataFileError(f"Permission denied while reading {path.name}.") from error


def save_json(path: Path, data: Any) -> None:
    """Write JSON atomically: write to a temp file, then swap it in.

    If the app crashes half-way, the original file is left untouched
    instead of being truncated.
    """
    path = Path(path)
    temp_name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        os.replace(temp_name, path)
        temp_name = None
    except PermissionError as error:
        raise DataFileError(f"Permission denied while saving {path.name}. Is it open in another program?") from error
    except OSError as error:
        raise DataFileError(f"Could not save {path.name}: {error.strerror or error}.") from error
    except TypeError as error:  # an object json cannot serialise
        raise DataFileError(f"Could not save {path.name}: {error}.") from error
    finally:
        if temp_name and os.path.exists(temp_name):
            os.remove(temp_name)


def backup_file(path: Path, suffix: str = ".corrupt") -> Path:
    """Copy a file aside (e.g. before replacing a corrupted one) and return the copy's path."""
    path = Path(path)
    backup = path.with_name(f"{path.stem}{suffix}{path.suffix}")
    try:
        shutil.copyfile(path, backup)
    except OSError as error:
        raise DataFileError(f"Could not back up {path.name}: {error.strerror or error}.") from error
    return backup


def read_csv(source: Path | IO) -> pd.DataFrame:
    """Read a CSV (path or uploaded file object) into a DataFrame of strings."""
    name = getattr(source, "name", str(source))
    try:
        # dtype=str keeps phone numbers and IDs exactly as written.
        frame = pd.read_csv(source, dtype=str, keep_default_na=False, skipinitialspace=True)
    except FileNotFoundError:
        raise DataFileError(f"Unable to find {Path(name).name}.") from None
    except pd.errors.EmptyDataError:
        raise DataFileError(f"{Path(name).name} is empty.") from None
    except pd.errors.ParserError as error:
        raise DataFileError(f"{Path(name).name} is not a valid CSV file: {error}") from error
    except UnicodeDecodeError as error:
        raise DataFileError(f"{Path(name).name} is not a UTF-8 CSV file.") from error
    frame.columns = [str(col).strip().lower().replace(" ", "_") for col in frame.columns]
    return frame


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False, encoding="utf-8")
    except PermissionError as error:
        raise DataFileError(f"Permission denied while writing {path.name}. Close it in Excel and try again.") from error
    except OSError as error:
        raise DataFileError(f"Could not write {path.name}: {error.strerror or error}.") from error
    return path


def write_text(text: str, path: Path) -> Path:
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as error:
        raise DataFileError(f"Could not write {path.name}: {error.strerror or error}.") from error
    return path
