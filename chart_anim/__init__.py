"""Turn a CSV into an animated line chart or bar race."""

from .io import CSVValidationError, load_csv, read_bar_race_csv, read_line_csv

__version__ = "0.1.0"

__all__ = [
    "CSVValidationError",
    "__version__",
    "load_csv",
    "read_bar_race_csv",
    "read_line_csv",
]
