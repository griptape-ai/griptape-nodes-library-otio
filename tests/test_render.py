import subprocess
from pathlib import Path

import pytest

from otio_nodes.media import FfmpegEncoder, url_to_path
from otio_nodes.render import RenderSettings, build_args, clips_to_render, render_movie

RATE = 24.0


def clip(name, start, duration, media=None, *, enabled=True):
    return {"id": name, "name": name, "start": start, "duration": duration, "enabled": enabled, "media": media}


def media(path, start=0, key=""):
    return {"url": str(path), "start": start, "duration": None, "key": key}


def timeline(video=(), audio=()):
    return {
        "rate": RATE,
        "tracks": [
            {"id": "v", "name": "Shots", "kind": "video", "role": "shots", "clips": list(video)},
            {"id": "a", "name": "Audio", "kind": "audio", "role": "audio", "clips": list(audio)},
        ],
    }


def test_clips_without_files_disabled_or_silence_are_left_out(tmp_path: Path):
    real = tmp_path / "a.mp4"
    real.write_bytes(b"x")
    model = timeline(
        video=[
            clip("real", 0, 24, media(real)),
            clip("missing", 24, 24, media(tmp_path / "nope.mp4")),
            clip("off", 48, 24, media(real), enabled=False),
            clip("none", 72, 24),
        ],
        audio=[clip("quiet", 0, 24, media(real, key="griptape:silence"))],
    )
    found = clips_to_render(model, url_to_path, RenderSettings())
    assert [c["name"] for c, _, _ in found] == ["real"]


def test_slates_can_be_left_out(tmp_path: Path):
    real = tmp_path / "slate.mov"
    real.write_bytes(b"x")
    model = timeline(video=[clip("s", 0, 24, media(real, key="griptape:slate-abc"))])
    assert clips_to_render(model, url_to_path, RenderSettings(include_slates=True))
    assert not clips_to_render(model, url_to_path, RenderSettings(include_slates=False))


def test_an_empty_timeline_and_odd_sizes_are_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="no clips"):
        render_movie(timeline(), url_to_path, tmp_path / "x.mp4")
    with pytest.raises(ValueError, match="even"):
        render_movie(timeline(video=[clip("a", 0, 24)]), url_to_path, tmp_path / "x.mp4", RenderSettings(width=101))


def test_with_no_sound_the_movie_still_gets_a_silent_track(tmp_path: Path):
    real = tmp_path / "a.mp4"
    real.write_bytes(b"x")
    model = timeline(video=[clip("a", 0, 24, media(real))])
    args = build_args(
        model,
        clips_to_render(model, url_to_path, RenderSettings()),
        lambda _: False,
        RenderSettings(),
        tmp_path / "o.mp4",
    )
    graph = args[args.index("-filter_complex") + 1]
    assert "anullsrc" in graph and "amix" not in graph


def _tools() -> tuple[str, str] | None:
    try:
        from static_ffmpeg import run

        ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
        return str(ffmpeg), str(ffprobe)
    except Exception:
        return None


@pytest.mark.skipif(_tools() is None, reason="ffmpeg is not available")
def test_real_render_puts_picture_and_sound_at_their_places(tmp_path: Path):
    tools = _tools()
    assert tools
    ffmpeg, ffprobe = tools
    encoder = FfmpegEncoder()
    red = tmp_path / "red.mp4"
    blue = tmp_path / "blue.mp4"
    tone = tmp_path / "tone.wav"
    for path, colour in ((red, "red"), (blue, "blue")):
        encoder._run(["-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=24:d=2", "-pix_fmt", "yuv420p", str(path)])
    encoder._run(["-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(tone)])

    # Red for 1 s, a 1 s gap, then blue for 1 s. A tone sounds from 2 s to 3 s, so it starts as blue starts.
    model = timeline(
        video=[clip("red", 0, 24, media(red)), clip("blue", 48, 24, media(blue))],
        audio=[clip("tone", 48, 24, media(tone))],
    )
    out = tmp_path / "out.mp4"
    used = render_movie(model, url_to_path, out, RenderSettings(width=320, height=180, crf=28))
    assert used == 3

    duration = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert abs(float(duration) - 3.0) < 0.1

    def pixel(second: float) -> tuple[int, int, int]:
        raw = subprocess.run(
            [ffmpeg, "-v", "error", "-ss", str(second), "-i", str(out), "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        ).stdout  # fmt: skip
        return raw[0], raw[1], raw[2]

    r, g, b = pixel(0.5)
    assert r > 180 and b < 80, "red at 0.5 s"
    r, g, b = pixel(1.5)
    assert r < 40 and g < 40 and b < 40, "black in the gap at 1.5 s"
    r, g, b = pixel(2.5)
    assert b > 180 and r < 80, "blue at 2.5 s"

    def loudness(start: float, length: float) -> float:
        result = subprocess.run(
            [ffmpeg, "-v", "info", "-ss", str(start), "-t", str(length), "-i", str(out), "-vn", "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, check=True,
        )  # fmt: skip
        line = next(x for x in result.stderr.splitlines() if "mean_volume" in x)
        return float(line.split("mean_volume:")[1].split("dB")[0])

    assert loudness(0.1, 1.5) < -60, "silent before the tone"
    assert loudness(2.1, 0.8) > -30, "the tone is heard from 2 s"
