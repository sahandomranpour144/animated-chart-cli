"""Frame rendering and output writing for chart_anim.

Frames are drawn with matplotlib's Agg canvas (no pyplot, no display needed)
and written as GIF with Pillow. MP4 is written through ffmpeg, only when the
output ends in .mp4 and ffmpeg is on PATH.

Line chart: the line is revealed from the first to the last point over
``duration_s`` seconds, with linear interpolation between data points.

Bar race: each CSV ``frame`` is a keyframe. Values and rank positions are
interpolated between consecutive keyframes, so bars slide past each other.
"""

from __future__ import annotations

import itertools
import shutil
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, date2num
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import blended_transform_factory
from PIL import Image

WIDTH_PX = 960
HEIGHT_PX = 540
DPI = 100
BG = "#FFFFFF"
INK = "#1B1F24"
MUTED = "#6B7280"
GRID = "#E5E7EB"
LINE_COLOR = "#1F6FEB"
PALETTE = (
    "#1F6FEB", "#E8590C", "#2B8A3E", "#9C36B5", "#C92A2A",
    "#0B7285", "#B08800", "#495057", "#D6336C", "#5C7CFA",
)
SUPPORTED_SUFFIXES = (".gif", ".mp4")


class OutputError(ValueError):
    """Raised when the requested output file cannot be produced."""


# ---------------------------------------------------------------- timing

def line_frame_count(fps: int, duration_s: float) -> int:
    """Number of frames in a line-chart animation (at least 2)."""
    return max(2, int(round(duration_s * fps)))


def line_reveal_positions(n_points: int, n_frames: int) -> np.ndarray:
    """Fractional row index revealed in each frame, from the first row to the last."""
    return np.linspace(0.0, n_points - 1, n_frames)


def bar_race_substeps(fps: int, transition_s: float) -> int:
    """Frames drawn between two consecutive keyframes."""
    return max(1, int(round(fps * transition_s)))


def bar_race_frame_count(n_keyframes: int, fps: int, transition_s: float) -> int:
    """Total frames in a bar-race animation, including the final keyframe."""
    return (n_keyframes - 1) * bar_race_substeps(fps, transition_s) + 1


# ---------------------------------------------------------------- ranking

def bar_race_keyframes(df: pd.DataFrame) -> tuple[list[int], list[str], np.ndarray]:
    """Pivot the long table into (frame labels, names, values[frame, name])."""
    wide = df.pivot(index="frame", columns="name", values="value").fillna(0.0)
    wide = wide.sort_index().sort_index(axis=1)
    labels = [int(f) for f in wide.index]
    names = [str(n) for n in wide.columns]
    return labels, names, wide.to_numpy(dtype=float)


def _ranking_indices(row: np.ndarray, names: list[str]) -> list[int]:
    """Indices ordered from largest to smallest value; ties broken alphabetically."""
    return sorted(range(len(names)), key=lambda i: (-row[i], names[i]))


def rank_order(row: np.ndarray, names: list[str]) -> list[str]:
    """Names ordered from largest to smallest value in one keyframe."""
    return [names[i] for i in _ranking_indices(row, names)]


def bar_race_order(df: pd.DataFrame) -> list[tuple[int, list[str]]]:
    """(frame label, names ranked top to bottom) for every keyframe, in frame order."""
    labels, names, values = bar_race_keyframes(df)
    return [(label, rank_order(values[k], names)) for k, label in enumerate(labels)]


def _positions(row: np.ndarray, names: list[str]) -> np.ndarray:
    """Rank position (0 = top bar) of each name in one keyframe."""
    pos = np.empty(len(names), dtype=float)
    pos[_ranking_indices(row, names)] = np.arange(len(names))
    return pos


# ---------------------------------------------------------------- frames

def iter_line_frames(
    df: pd.DataFrame, *, fps: int, duration_s: float, title: str | None = None
) -> Iterator[np.ndarray]:
    """Yield RGB frames (H, W, 3 uint8) of the line being revealed."""
    x = date2num(df["date"].dt.to_pydatetime())
    y = df["value"].to_numpy(dtype=float)
    n = len(y)
    span = float(y.max() - y.min())
    pad = span * 0.12 if span > 0 else max(abs(float(y.max())), 1.0) * 0.1
    ylim = (float(y.min()) - pad, float(y.max()) + pad)

    fig, ax = _new_figure(left=0.08)
    for t in line_reveal_positions(n, line_frame_count(fps, duration_s)):
        i = min(int(np.floor(t)), n - 2)
        frac = t - i
        xs = np.append(x[: i + 1], x[i] + frac * (x[i + 1] - x[i]))
        ys = np.append(y[: i + 1], y[i] + frac * (y[i + 1] - y[i]))

        ax.clear()
        _style_line_axes(ax, (float(x[0]), float(x[-1])), ylim, title)
        ax.plot(xs, ys, color=LINE_COLOR, linewidth=3, solid_capstyle="round")
        ax.scatter(xs[-1:], ys[-1:], s=70, color=LINE_COLOR, zorder=3)
        ax.annotate(
            f"{ys[-1]:,.2f}",
            xy=(xs[-1], ys[-1]),
            xytext=(10, 10),
            textcoords="offset points",
            color=INK,
            fontsize=14,
            fontweight="bold",
        )
        yield _grab(fig)


def iter_bar_race_frames(
    df: pd.DataFrame,
    *,
    fps: int,
    transition_s: float,
    top: int,
    title: str | None = None,
) -> Iterator[np.ndarray]:
    """Yield RGB frames of the bar race, interpolating between keyframes."""
    labels, names, values = bar_race_keyframes(df)
    n_keys = len(labels)
    positions = np.stack([_positions(values[k], names) for k in range(n_keys)])
    top = min(top, len(names))
    vmax = float(values.max()) * 1.18
    if vmax <= 0:
        vmax = 1.0
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(names))]
    substeps = bar_race_substeps(fps, transition_s)

    fig, ax = _new_figure(left=0.25)
    label_transform = blended_transform_factory(ax.transAxes, ax.transData)

    def draw(k: int, s: float) -> np.ndarray:
        k2 = min(k + 1, n_keys - 1)
        vals = (1 - s) * values[k] + s * values[k2]
        pos = (1 - s) * positions[k] + s * positions[k2]
        label = round(labels[k] + s * (labels[k2] - labels[k]))

        ax.clear()
        _style_bar_axes(ax, top, vmax, title)
        for i in np.argsort(pos, kind="stable"):
            if pos[i] >= top:
                continue
            ax.barh(pos[i], vals[i], height=0.8, color=colors[i], zorder=2)
            ax.text(-0.01, pos[i], names[i], transform=label_transform,
                    ha="right", va="center", fontsize=14, color=INK)
            ax.text(vals[i] + vmax * 0.01, pos[i], f"{vals[i]:,.0f}",
                    ha="left", va="center", fontsize=13, color=INK)
        ax.text(0.99, 0.08, f"{label}", transform=ax.transAxes, ha="right", va="bottom",
                fontsize=48, fontweight="bold", color=MUTED)
        return _grab(fig)

    for k in range(n_keys - 1):
        for j in range(substeps):
            yield draw(k, j / substeps)
    yield draw(n_keys - 1, 0.0)


# ---------------------------------------------------------------- output

def ensure_output_supported(path: str | Path) -> None:
    """Check the output path before rendering, so bad options fail fast."""
    out = Path(path)
    if out.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise OutputError(f"unsupported output type {out.suffix!r}; use .gif or .mp4")
    if not out.parent.is_dir():
        raise OutputError(f"output folder does not exist: {out.parent}")
    if out.suffix.lower() == ".mp4" and shutil.which("ffmpeg") is None:
        raise OutputError("MP4 output needs ffmpeg on PATH; install ffmpeg or use a .gif output")


def write_animation(frames: Iterable[np.ndarray], out_path: str | Path, fps: int) -> int:
    """Write frames to a GIF (Pillow) or MP4 (ffmpeg). Returns the number of frames written."""
    out = Path(out_path)
    ensure_output_supported(out)
    if out.suffix.lower() == ".gif":
        return _write_gif(frames, out, fps)
    return _write_mp4(frames, out, fps)


def _write_gif(frames: Iterable[np.ndarray], out: Path, fps: int) -> int:
    images = [Image.fromarray(f).quantize(colors=256) for f in frames]
    if not images:
        raise ValueError("no frames to write")
    images[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=round(1000 / fps),
        loop=0,
    )
    return len(images)


def _write_mp4(frames: Iterable[np.ndarray], out: Path, fps: int) -> int:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise OutputError("MP4 output needs ffmpeg on PATH")
    it = iter(frames)
    first = next(it, None)
    if first is None:
        raise ValueError("no frames to write")
    height, width = first.shape[:2]
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    count = 0
    try:
        for frame in itertools.chain([first], it):
            proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
            count += 1
    finally:
        proc.stdin.close()
        returncode = proc.wait()
    if returncode != 0:
        raise RuntimeError(f"ffmpeg exited with code {returncode}")
    return count


# ---------------------------------------------------------------- drawing helpers

def _new_figure(left: float):
    fig = Figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=BG)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=left, right=0.96, top=0.86, bottom=0.12)
    return fig, ax


def _grab(fig: Figure) -> np.ndarray:
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())
    return rgba[..., :3].copy()


def _style_line_axes(ax, xlim, ylim, title) -> None:
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    locator = AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    ax.set_facecolor(BG)
    ax.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=12)
    if title:
        ax.set_title(title, loc="left", color=INK, fontsize=18, fontweight="bold", pad=16)


def _style_bar_axes(ax, top: int, vmax: float, title) -> None:
    ax.set_xlim(0, vmax)
    ax.set_ylim(top - 0.5, -0.5)
    ax.set_yticks([])
    ax.set_facecolor(BG)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:,.0f}"))
    ax.tick_params(colors=MUTED, labelsize=11, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, loc="left", color=INK, fontsize=18, fontweight="bold", pad=16)
