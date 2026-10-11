"""Command-line entry point.

    python -m chart_anim input.csv -o out.gif --type line --fps 12
    python -m chart_anim races.csv -o race.gif --type bar-race --fps 12

Exit codes: 0 success, 2 invalid input or options, 1 unexpected I/O failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .io import CSVValidationError, load_csv
from .render import (
    OutputError,
    ensure_output_supported,
    iter_bar_race_frames,
    iter_line_frames,
    write_animation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chart_anim",
        description="Turn a CSV into an animated line chart or bar race (GIF, or MP4 if ffmpeg is installed).",
    )
    parser.add_argument(
        "input", type=Path,
        help="CSV with columns date,value (line) or frame,name,value (bar-race)",
    )
    parser.add_argument("-o", "--output", required=True, type=Path, help="output file, .gif or .mp4")
    parser.add_argument(
        "--type", dest="chart_type", choices=("line", "bar-race"), default="line",
        help="chart type (default: line)",
    )
    parser.add_argument("--fps", type=int, default=12, help="frames per second, 1-60 (default: 12)")
    parser.add_argument(
        "--duration", type=float, default=6.0,
        help="line chart: seconds for the full reveal (default: 6)",
    )
    parser.add_argument(
        "--transition", type=float, default=0.5,
        help="bar race: seconds between two frames (default: 0.5)",
    )
    parser.add_argument("--top", type=int, default=10, help="bar race: bars shown at once (default: 10)")
    parser.add_argument("--title", default=None, help="optional chart title")
    return parser


def _option_error(args: argparse.Namespace) -> str | None:
    if not 1 <= args.fps <= 60:
        return "--fps must be between 1 and 60"
    if args.duration <= 0:
        return "--duration must be greater than 0"
    if args.transition <= 0:
        return "--transition must be greater than 0"
    if args.top < 1:
        return "--top must be at least 1"
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    problem = _option_error(args)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    try:
        df = load_csv(args.input, args.chart_type)
        ensure_output_supported(args.output)
        if args.chart_type == "line":
            frames = iter_line_frames(df, fps=args.fps, duration_s=args.duration, title=args.title)
        else:
            frames = iter_bar_race_frames(
                df, fps=args.fps, transition_s=args.transition, top=args.top, title=args.title
            )
        count = write_animation(frames, args.output, args.fps)
    except (CSVValidationError, OutputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: could not write output: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {count} frames to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
