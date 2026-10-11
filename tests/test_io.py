import pytest

from chart_anim.io import CSVValidationError, read_bar_race_csv, read_line_csv


def write(tmp_path, text, name="input.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_line_csv_loads_and_sorts_by_date(tmp_path):
    path = write(tmp_path, "date,value\n2024-03-01,3\n2024-01-01,1\n2024-02-01,2\n")
    df = read_line_csv(path)
    assert list(df["value"]) == [1.0, 2.0, 3.0]
    assert df["date"].is_monotonic_increasing


def test_line_csv_missing_column(tmp_path):
    path = write(tmp_path, "date,price\n2024-01-01,1\n2024-02-01,2\n")
    with pytest.raises(CSVValidationError, match="missing required column.*value"):
        read_line_csv(path)


def test_line_csv_non_numeric_value_reports_row(tmp_path):
    path = write(tmp_path, "date,value\n2024-01-01,1\n2024-02-01,abc\n")
    with pytest.raises(CSVValidationError, match="'value'.*row 2"):
        read_line_csv(path)


def test_line_csv_empty_value_is_rejected(tmp_path):
    path = write(tmp_path, "date,value\n2024-01-01,1\n2024-02-01,\n")
    with pytest.raises(CSVValidationError, match="must be a finite number"):
        read_line_csv(path)


def test_line_csv_bad_date(tmp_path):
    path = write(tmp_path, "date,value\nnot-a-date,1\n2024-02-01,2\n")
    with pytest.raises(CSVValidationError, match="'date'.*row 1"):
        read_line_csv(path)


def test_line_csv_empty_file(tmp_path):
    path = write(tmp_path, "")
    with pytest.raises(CSVValidationError, match="empty"):
        read_line_csv(path)


def test_line_csv_header_only(tmp_path):
    path = write(tmp_path, "date,value\n")
    with pytest.raises(CSVValidationError, match="no data rows"):
        read_line_csv(path)


def test_line_csv_needs_two_points(tmp_path):
    path = write(tmp_path, "date,value\n2024-01-01,1\n")
    with pytest.raises(CSVValidationError, match="at least 2 data rows"):
        read_line_csv(path)


def test_missing_file(tmp_path):
    with pytest.raises(CSVValidationError, match="not found"):
        read_line_csv(tmp_path / "nope.csv")


def test_bar_race_missing_column(tmp_path):
    path = write(tmp_path, "frame,name\n1,A\n2,A\n")
    with pytest.raises(CSVValidationError, match="missing required column.*value"):
        read_bar_race_csv(path)


def test_bar_race_fractional_frame(tmp_path):
    path = write(tmp_path, "frame,name,value\n1.5,A,1\n2,A,2\n")
    with pytest.raises(CSVValidationError, match="'frame'.*whole number"):
        read_bar_race_csv(path)


def test_bar_race_negative_value(tmp_path):
    path = write(tmp_path, "frame,name,value\n1,A,-1\n2,A,2\n")
    with pytest.raises(CSVValidationError, match="zero or positive"):
        read_bar_race_csv(path)


def test_bar_race_duplicate_pair(tmp_path):
    path = write(tmp_path, "frame,name,value\n1,A,1\n1,A,2\n2,A,3\n")
    with pytest.raises(CSVValidationError, match="duplicate rows"):
        read_bar_race_csv(path)


def test_bar_race_needs_two_frames(tmp_path):
    path = write(tmp_path, "frame,name,value\n1,A,1\n1,B,2\n")
    with pytest.raises(CSVValidationError, match="at least 2 distinct frame"):
        read_bar_race_csv(path)
