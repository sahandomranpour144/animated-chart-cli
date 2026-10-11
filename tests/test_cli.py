from PIL import Image

import chart_anim.render as render
from chart_anim.__main__ import main
from chart_anim.render import bar_race_frame_count, line_frame_count


def gif_frame_count(path):
    with Image.open(path) as im:
        return im.n_frames


def test_line_cli_writes_gif_with_expected_frames(tmp_path, capsys):
    src = tmp_path / "line.csv"
    src.write_text("date,value\n" + "\n".join(f"2024-01-{d:02d},{d * 1.5}" for d in range(1, 21)) + "\n")
    out = tmp_path / "line.gif"

    code = main([str(src), "-o", str(out), "--type", "line", "--fps", "8", "--duration", "1"])

    assert code == 0
    assert out.exists()
    assert gif_frame_count(out) == line_frame_count(fps=8, duration_s=1) == 8
    assert "wrote 8 frames" in capsys.readouterr().out


def test_bar_race_cli_writes_gif_with_expected_frames(tmp_path):
    src = tmp_path / "race.csv"
    src.write_text(
        "frame,name,value\n"
        "1,A,10\n1,B,30\n1,C,20\n"
        "2,A,25\n2,B,15\n2,C,20\n"
        "3,A,40\n3,B,5\n3,C,35\n"
    )
    out = tmp_path / "race.gif"

    code = main([str(src), "-o", str(out), "--type", "bar-race", "--fps", "8",
                 "--transition", "0.25", "--top", "3"])

    assert code == 0
    assert gif_frame_count(out) == bar_race_frame_count(n_keyframes=3, fps=8, transition_s=0.25) == 5


def test_invalid_csv_exits_with_code_2(tmp_path, capsys):
    src = tmp_path / "bad.csv"
    src.write_text("date,value\n2024-01-01,oops\n2024-01-02,2\n")

    code = main([str(src), "-o", str(tmp_path / "out.gif")])

    assert code == 2
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "out.gif").exists()


def test_missing_input_exits_with_code_2(tmp_path, capsys):
    code = main([str(tmp_path / "missing.csv"), "-o", str(tmp_path / "out.gif")])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_unsupported_output_suffix_exits_with_code_2(tmp_path, capsys):
    src = tmp_path / "line.csv"
    src.write_text("date,value\n2024-01-01,1\n2024-01-02,2\n")
    code = main([str(src), "-o", str(tmp_path / "out.png")])
    assert code == 2
    assert "unsupported output type" in capsys.readouterr().err


def test_fps_out_of_range_exits_with_code_2(tmp_path, capsys):
    src = tmp_path / "line.csv"
    src.write_text("date,value\n2024-01-01,1\n2024-01-02,2\n")
    code = main([str(src), "-o", str(tmp_path / "out.gif"), "--fps", "0"])
    assert code == 2
    assert "--fps" in capsys.readouterr().err


def test_mp4_without_ffmpeg_exits_with_code_2(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(render.shutil, "which", lambda name: None)
    src = tmp_path / "line.csv"
    src.write_text("date,value\n2024-01-01,1\n2024-01-02,2\n")
    code = main([str(src), "-o", str(tmp_path / "out.mp4")])
    assert code == 2
    assert "ffmpeg" in capsys.readouterr().err
