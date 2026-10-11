import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from chart_anim.io import read_bar_race_csv
from chart_anim.render import (
    bar_race_frame_count,
    bar_race_order,
    iter_bar_race_frames,
    iter_line_frames,
    line_frame_count,
    line_reveal_positions,
    rank_order,
)


def make_line_df(n=20):
    dates = pd.date_range("2022-01-01", periods=n, freq="D")
    values = np.sin(np.linspace(0, 3, n)) * 10 + 50
    return pd.DataFrame({"date": dates, "value": values})


def make_race_df():
    # Leader changes between frames 1, 2 and 3, so the ordering is not trivially constant.
    rows = [
        (1, "A", 10), (1, "B", 30), (1, "C", 20),
        (2, "A", 25), (2, "B", 15), (2, "C", 20),
        (3, "A", 40), (3, "B", 5), (3, "C", 35),
    ]
    return pd.DataFrame(rows, columns=["frame", "name", "value"])


def test_line_frame_count_from_duration_and_fps():
    assert line_frame_count(fps=12, duration_s=2) == 24
    assert line_frame_count(fps=10, duration_s=0.01) == 2  # never fewer than 2


def test_line_reveal_runs_from_first_to_last_point():
    t = line_reveal_positions(n_points=20, n_frames=30)
    assert len(t) == 30
    assert t[0] == 0.0
    assert t[-1] == 19.0
    assert np.all(np.diff(t) > 0)


def test_line_frames_count_and_shape():
    df = make_line_df()
    frames = list(iter_line_frames(df, fps=12, duration_s=1.0))
    assert len(frames) == line_frame_count(12, 1.0) == 12
    assert frames[0].shape == (540, 960, 3)
    assert frames[0].dtype == np.uint8


def test_bar_race_keyframe_order_follows_frame_column():
    df = read_bar_race_csv_from_df(make_race_df())
    order = bar_race_order(df)
    assert [label for label, _ in order] == [1, 2, 3]


def test_bar_race_each_keyframe_ranks_by_value_descending():
    df = read_bar_race_csv_from_df(make_race_df())
    expected = {1: ["B", "C", "A"], 2: ["A", "C", "B"], 3: ["A", "C", "B"]}
    for label, names in bar_race_order(df):
        assert names == expected[label]
        values = df[df["frame"] == label].set_index("name")["value"]
        assert list(values[names]) == sorted(values, reverse=True)


def test_rank_order_breaks_ties_alphabetically():
    assert rank_order(np.array([5.0, 5.0, 1.0]), ["Zed", "Amy", "Bo"]) == ["Amy", "Zed", "Bo"]


def test_bar_race_frame_count_includes_interpolated_steps():
    assert bar_race_frame_count(n_keyframes=3, fps=8, transition_s=0.25) == 5  # 2 steps x 2 + 1
    df = make_race_df()
    frames = list(iter_bar_race_frames(df, fps=8, transition_s=0.25, top=3))
    assert len(frames) == 5


def read_bar_race_csv_from_df(df):
    """Round-trip a frame through the real CSV reader so validation is part of the test."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "race.csv"
        df.to_csv(path, index=False)
        return read_bar_race_csv(path)
