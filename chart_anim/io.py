"""CSV loading and validation for chart_anim.

Two input layouts are supported:

* line:      ``date,value``           one row per point, revealed over time
* bar-race:  ``frame,name,value``     one row per (frame, name) bar value

Every problem is reported as a CSVValidationError with the offending data
row number, so the CLI can print a clear message and exit with code 2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

LINE_COLUMNS = ("date", "value")
BAR_RACE_COLUMNS = ("frame", "name", "value")
MAX_REPORTED_ROWS = 5


class CSVValidationError(ValueError):
    """Raised when an input CSV is missing, empty, or malformed."""


def read_line_csv(path: str | Path) -> pd.DataFrame:
    """Load a ``date,value`` CSV. Returns columns ``date`` (datetime) and ``value`` (float), sorted by date."""
    raw = _read_raw(path, LINE_COLUMNS)
    date_text = _stripped(raw["date"])
    dates = pd.to_datetime(date_text, errors="coerce", format="mixed")
    _reject(raw, dates.isna().to_numpy(), "date", "must be a valid date such as 2024-01-31")
    values = _numeric(raw, "value")

    df = pd.DataFrame({"date": dates, "value": values})
    df = df.sort_values("date", kind="stable").reset_index(drop=True)
    if len(df) < 2:
        raise CSVValidationError("line chart needs at least 2 data rows")
    if df["date"].nunique() < 2:
        raise CSVValidationError("line chart needs at least 2 distinct dates")
    return df


def read_bar_race_csv(path: str | Path) -> pd.DataFrame:
    """Load a ``frame,name,value`` CSV. Returns integer ``frame``, string ``name``, float ``value`` (>= 0)."""
    raw = _read_raw(path, BAR_RACE_COLUMNS)
    names = _stripped(raw["name"])
    _reject(raw, (names == "").to_numpy(), "name", "must not be empty")

    frames = _numeric(raw, "frame")
    _reject(raw, ~np.isclose(frames, np.round(frames)), "frame", "must be a whole number")

    values = _numeric(raw, "value")
    _reject(raw, values < 0, "value", "must be zero or positive for a bar race")

    df = pd.DataFrame(
        {"frame": np.round(frames).astype(np.int64), "name": names.to_numpy(), "value": values}
    )
    dup = df.duplicated(["frame", "name"], keep=False)
    if dup.any():
        first = df[dup].iloc[0]
        raise CSVValidationError(
            f"duplicate rows for frame={first['frame']}, name={first['name']!r}; "
            "each (frame, name) pair must appear once"
        )
    if df["frame"].nunique() < 2:
        raise CSVValidationError("bar race needs at least 2 distinct frame values")
    return df.sort_values(["frame", "name"]).reset_index(drop=True)


def load_csv(path: str | Path, chart_type: str) -> pd.DataFrame:
    """Dispatch to the reader for ``chart_type`` ('line' or 'bar-race')."""
    if chart_type == "line":
        return read_line_csv(path)
    if chart_type == "bar-race":
        return read_bar_race_csv(path)
    raise ValueError(f"unknown chart type {chart_type!r}; use 'line' or 'bar-race'")


def _read_raw(path: str | Path, required: tuple[str, ...]) -> pd.DataFrame:
    """Read every column as text and check the header and that rows exist."""
    p = Path(path)
    if not p.is_file():
        raise CSVValidationError(f"input file not found: {p}")
    try:
        raw = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        raise CSVValidationError(f"input file is empty: {p}") from None
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise CSVValidationError(f"could not parse CSV {p}: {exc}") from None

    raw.columns = [str(c).strip() for c in raw.columns]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        found = ", ".join(raw.columns) or "(none)"
        raise CSVValidationError(
            f"missing required column(s): {', '.join(missing)} (found: {found})"
        )
    if raw.empty:
        raise CSVValidationError(f"no data rows in {p}")
    return raw


def _stripped(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def _numeric(raw: pd.DataFrame, column: str) -> np.ndarray:
    """Convert a column to finite floats, rejecting anything else with its row number."""
    values = pd.to_numeric(_stripped(raw[column]), errors="coerce")
    arr = values.to_numpy(dtype=float, na_value=np.nan)
    _reject(raw, ~np.isfinite(arr), column, "must be a finite number")
    return arr


def _reject(raw: pd.DataFrame, bad_mask, column: str, reason: str) -> None:
    """Raise if any data row is flagged in ``bad_mask``; name up to MAX_REPORTED_ROWS of them."""
    bad_rows = np.flatnonzero(np.asarray(bad_mask, dtype=bool))
    if bad_rows.size == 0:
        return
    shown = ", ".join(
        f"row {r + 1} ({column}={raw[column].iat[r]!r})" for r in bad_rows[:MAX_REPORTED_ROWS]
    )
    extra = bad_rows.size - MAX_REPORTED_ROWS
    suffix = f" (+{extra} more)" if extra > 0 else ""
    raise CSVValidationError(f"column '{column}' {reason}: {shown}{suffix}")
