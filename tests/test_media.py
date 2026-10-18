import copy
import shutil
import subprocess
from pathlib import Path

import pytest

from otio_nodes.breakdown import breakdown
from otio_nodes.fountain import parse
from otio_nodes.media import FfmpegEncoder, draw_slate, ensure_media, link_media, slate_text, url_to_path
from otio_nodes.model import build_model, validate_model
from otio_nodes.otio_io import from_json, to_json

TEXT = """Title: Test

INT. ROOM - DAY

JACK
Hello there my good friend today.

CLOSE UP of Jack.

JILL
Hi.
"""


class FakeEncoder:
    def __init__(self):
        self.slates: list[tuple[str, int]] = []
        self.silences: list[int] = []

    def slate(self, text, path, frames, rate):
        path.write_bytes(b"slate")
        self.slates.append((path.name, frames))

    def silence(self, path, frames, rate):
        path.write_bytes(b"silence")
        self.silences.append(frames)


def make_model() -> dict:
    return build_model(breakdown(parse(TEXT)))


def clips(model: dict, role: str) -> list[dict]:
    return [c for t in model["tracks"] if t["role"] == role for c in t["clips"]]


def test_every_owned_clip_gets_media_with_handles(tmp_path):
    encoder = FakeEncoder()
    model = ensure_media(make_model(), tmp_path / "media", handle_seconds=2.0, encoder=encoder)
    for clip in clips(model, "shots"):
        assert clip["media"]["start"] == 48
        assert clip["media"]["duration"] == clip["duration"] + 96
        assert url_to_path(clip["media"]["url"]).exists()
    audio = [c for t in model["tracks"] if t["kind"] == "audio" for c in t["clips"]]
    assert audio and {c["media"]["url"] for c in audio} == {audio[0]["media"]["url"]}
    assert len(encoder.slates) == 2
    assert len(encoder.silences) == 1
    validate_model(model)


def test_original_model_is_not_changed(tmp_path):
    model = make_model()
    before = copy.deepcopy(model)
    ensure_media(model, tmp_path / "media", encoder=FakeEncoder())
    assert model == before


def test_existing_media_is_reused(tmp_path):
    first = ensure_media(make_model(), tmp_path / "media", encoder=FakeEncoder())
    encoder = FakeEncoder()
    again = ensure_media(first, tmp_path / "media", encoder=encoder)
    assert encoder.slates == [] and encoder.silences == []
    assert again == first


def test_slate_is_remade_when_text_changes_or_clip_outgrows_handles(tmp_path):
    first = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())

    edited = copy.deepcopy(first)
    clips(edited, "shots")[0]["description"] = "A new description."
    encoder = FakeEncoder()
    ensure_media(edited, tmp_path / "media", handle_seconds=1.0, encoder=encoder)
    assert [name.split("_")[1] for name, _ in encoder.slates] == ["shot-001"]

    grown = copy.deepcopy(first)
    shot = clips(grown, "shots")[1]
    shot["duration"] += 100
    encoder = FakeEncoder()
    ensure_media(grown, tmp_path / "media", handle_seconds=1.0, encoder=encoder)
    assert [name.split("_")[1] for name, _ in encoder.slates] == ["shot-002"]


def test_shorter_clip_keeps_its_media(tmp_path):
    first = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())
    trimmed = copy.deepcopy(first)
    clips(trimmed, "shots")[0]["duration"] -= 5
    encoder = FakeEncoder()
    ensure_media(trimmed, tmp_path / "media", handle_seconds=1.0, encoder=encoder)
    assert encoder.slates == []


def test_silence_is_remade_when_an_audio_clip_outgrows_it(tmp_path):
    first = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())
    grown = copy.deepcopy(first)
    audio = next(t for t in grown["tracks"] if t["kind"] == "audio" and t["clips"])["clips"][0]
    audio["duration"] += 500
    encoder = FakeEncoder()
    result = ensure_media(grown, tmp_path / "media", handle_seconds=1.0, encoder=encoder)
    assert len(encoder.silences) == 1
    validate_model(result)


def test_foreign_media_is_left_alone(tmp_path):
    model = make_model()
    shot = clips(model, "shots")[0]
    shot["media"] = {"url": "file:///somewhere/plate.mov", "start": 0, "duration": shot["duration"], "key": ""}
    result = ensure_media(model, tmp_path / "media", encoder=FakeEncoder())
    assert clips(result, "shots")[0]["media"] == shot["media"]
    assert clips(result, "shots")[1]["media"]["key"].startswith("griptape:")


def test_no_folder_when_nothing_to_make(tmp_path):
    model = {"title": "", "rate": 24.0, "tracks": [], "markers": []}
    ensure_media(model, tmp_path / "media", encoder=FakeEncoder())
    assert not (tmp_path / "media").exists()


def test_negative_handles_rejected(tmp_path):
    with pytest.raises(ValueError, match="handle_seconds"):
        ensure_media(make_model(), tmp_path / "media", handle_seconds=-1, encoder=FakeEncoder())


def test_slate_text_and_drawing():
    shot = clips(make_model(), "shots")[0]
    text = slate_text(shot)
    assert text["title"] == shot["name"]
    assert text["subtitle"].startswith("SQ01")
    assert draw_slate(text).size == (1280, 720)


def test_media_survives_the_otio_round_trip(tmp_path):
    model = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())
    assert from_json(to_json(model)) == model


def test_otio_clips_use_external_references(tmp_path):
    import opentimelineio as otio

    from otio_nodes.otio_io import model_to_otio

    model = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())
    timeline = model_to_otio(model)
    clip = timeline.tracks[0][0]
    assert isinstance(clip.media_reference, otio.schema.ExternalReference)
    assert clip.media_reference.target_url.startswith("file://")
    assert clip.source_range.start_time.value == 24
    assert clip.media_reference.available_range.duration.value == clip.source_range.duration.value + 48
    assert all(isinstance(c.media_reference, otio.schema.ExternalReference) for c in timeline.find_clips())


def test_a_slate_the_clip_outgrew_is_not_a_validation_error(tmp_path):
    model = ensure_media(make_model(), tmp_path / "media", handle_seconds=0.0, encoder=FakeEncoder())
    clips(model, "shots")[-1]["duration"] += 10
    validate_model(model)  # saving remakes the slate, so it must not stop the save


def test_saving_remakes_a_slate_the_clip_outgrew(tmp_path):
    from otio_nodes.node_helpers import save_timeline

    _, model = save_timeline(make_model(), tmp_path, handle_seconds=1.0, encoder=FakeEncoder())
    shot = clips(model, "shots")[-1]
    shot["duration"] += 100
    _, saved = save_timeline(model, tmp_path, handle_seconds=1.0, encoder=FakeEncoder())
    media = clips(saved, "shots")[-1]["media"]
    assert media["start"] + shot["duration"] <= media["duration"]


def test_linked_length_is_not_cut_short_by_float_error():
    model = linked_model("/plate.mov")
    model["rate"] = 25.0
    linked = link_media(model, lambda url: Path(__file__), lambda path: 4.6)  # 4.6 * 25 is 114.99999999999999
    assert clips(linked, "shots")[0]["media"]["duration"] == 115


def _ffprobe() -> str | None:
    try:
        from static_ffmpeg import run

        return str(run.get_or_fetch_platform_executables_else_raise()[1])
    except Exception:
        return shutil.which("ffprobe")


@pytest.mark.skipif(_ffprobe() is None, reason="ffmpeg is not available")
def test_real_ffmpeg_makes_a_slate_and_silence_of_the_right_length(tmp_path):
    ffprobe = _ffprobe()
    assert ffprobe
    encoder = FfmpegEncoder()
    slate = tmp_path / "slate.mov"
    encoder.slate(
        {"title": "001 Wide Shot", "subtitle": "SQ01  INT. ROOM - DAY", "body": "Jonh jumps out of bed."},
        slate,
        48,
        24.0,
    )
    frames = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(slate),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert frames == "48"
    assert slate.stat().st_size < 200_000

    silence = tmp_path / "silence.mov"
    encoder.silence(silence, 96, 24.0)
    duration = float(
        subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(silence)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    assert duration == pytest.approx(4.0, abs=0.1)


def test_missing_ffmpeg_gives_a_clear_error(tmp_path):
    encoder = FfmpegEncoder(ffmpeg=str(tmp_path / "no-such-ffmpeg"))
    with pytest.raises((ValueError, FileNotFoundError)):
        encoder.silence(tmp_path / "x.mov", 24, 24.0)


def test_url_to_path_decodes_file_urls():
    assert Path(url_to_path("file:///tmp/a%20b.mov")) == Path("/tmp/a b.mov")


def test_editing_text_makes_a_new_slate_and_never_overwrites_the_old_one(tmp_path):
    first = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())
    old_path = url_to_path(clips(first, "shots")[0]["media"]["url"])
    old_path.write_bytes(b"the old slate, as another timeline still sees it")

    edited = copy.deepcopy(first)
    clips(edited, "shots")[0]["description"] = "A new description."
    second = ensure_media(edited, tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())

    new_path = url_to_path(clips(second, "shots")[0]["media"]["url"])
    assert new_path != old_path and new_path.exists()
    assert old_path.read_bytes() == b"the old slate, as another timeline still sees it"
    assert url_to_path(clips(first, "shots")[0]["media"]["url"]).read_bytes().startswith(b"the old slate")


def test_a_clip_that_grows_gets_a_new_file_not_a_longer_copy_of_the_old_one(tmp_path):
    first = ensure_media(make_model(), tmp_path / "media", handle_seconds=0.0, encoder=FakeEncoder())
    old_path = url_to_path(clips(first, "shots")[0]["media"]["url"])
    grown = copy.deepcopy(first)
    clips(grown, "shots")[0]["duration"] += 50
    second = ensure_media(grown, tmp_path / "media", handle_seconds=0.0, encoder=FakeEncoder())
    assert url_to_path(clips(second, "shots")[0]["media"]["url"]) != old_path
    assert old_path.exists()


def test_a_file_that_already_exists_is_never_written_over(tmp_path):
    model = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())
    path = url_to_path(clips(model, "shots")[0]["media"]["url"])
    path.write_bytes(b"sentinel")
    forgotten = copy.deepcopy(model)
    for track in forgotten["tracks"]:
        for clip in track["clips"]:
            clip["media"] = None
    encoder = FakeEncoder()
    again = ensure_media(forgotten, tmp_path / "media", handle_seconds=1.0, encoder=encoder)
    assert encoder.slates == [] and encoder.silences == [], "nothing is made again when the file is already there"
    assert path.read_bytes() == b"sentinel"
    assert clips(again, "shots")[0]["media"]["url"] == model["tracks"][0]["clips"][0]["media"]["url"]


def test_linked_media_is_never_touched_when_text_changes(tmp_path):
    model = make_model()
    linked = {
        "url": "file:///somewhere/plate.mov",
        "start": 0,
        "duration": clips(model, "shots")[0]["duration"],
        "key": "",
    }
    clips(model, "shots")[0]["media"] = linked
    clips(model, "shots")[0]["name"] = "Renamed"
    clips(model, "shots")[0]["description"] = "Edited description"
    encoder = FakeEncoder()
    result = ensure_media(model, tmp_path / "media", handle_seconds=1.0, encoder=encoder)
    assert clips(result, "shots")[0]["media"] == linked
    assert all(name.split("_")[1] != "shot-001" for name, _ in encoder.slates)


def linked_model(path: str, **media) -> dict:
    model = make_model()
    shot = clips(model, "shots")[0]
    shot["media"] = {"url": path, "start": 24, "duration": None, "key": "", **media}
    return model


def resolver(base: Path):
    def resolve(url: str) -> Path:
        return Path(url_to_path(url)) if url.startswith("file:") else base / url.lstrip("/")

    return resolve


def test_linked_media_is_resolved_checked_and_measured(tmp_path):
    from otio_nodes.media import link_media

    plate = tmp_path / "plate.mov"
    plate.write_bytes(b"x")
    model = linked_model("plate.mov")
    result = link_media(model, resolver(tmp_path), probe=lambda path: 10.5)
    media = clips(result, "shots")[0]["media"]
    assert media["url"] == plate.resolve().as_uri()
    assert media["start"] == 24
    assert media["duration"] == 252, "10.5 s at 24 fps, whole frames"
    assert media["key"] == ""
    assert clips(model, "shots")[0]["media"]["url"] == "plate.mov", "the original model is not changed"


def test_a_length_that_cannot_be_measured_stays_unknown(tmp_path):
    from otio_nodes.media import link_media

    (tmp_path / "still.png").write_bytes(b"x")
    result = link_media(linked_model("still.png"), resolver(tmp_path), probe=lambda path: None)
    assert clips(result, "shots")[0]["media"]["duration"] is None


def test_linked_media_that_is_missing_is_reported_by_clip(tmp_path):
    from otio_nodes.media import link_media

    model = linked_model("not_there.mov")
    clips(model, "shots")[1]["media"] = {"url": "also_missing.mov", "start": 0, "duration": None, "key": ""}
    with pytest.raises(ValueError, match="nothing was saved") as error:
        link_media(model, resolver(tmp_path), probe=lambda path: 1.0)
    message = str(error.value)
    assert "not_there.mov" in message and "also_missing.mov" in message
    assert message.count("clip '") == 2


def test_a_resolver_that_fails_is_reported_not_raised_raw(tmp_path):
    from otio_nodes.media import link_media

    def broken(url: str):
        msg = "no project is loaded"
        raise RuntimeError(msg)

    with pytest.raises(ValueError, match="no project is loaded"):
        link_media(linked_model("{inputs}/plate.mov"), broken, probe=lambda path: 1.0)


def test_placeholder_slates_are_left_alone_by_linking(tmp_path):
    from otio_nodes.media import link_media

    model = ensure_media(make_model(), tmp_path / "media", handle_seconds=1.0, encoder=FakeEncoder())
    before = copy.deepcopy(model)
    assert link_media(model, resolver(tmp_path), probe=lambda path: 99.0) == before


def test_an_unknown_length_is_written_without_an_available_range_and_validates(tmp_path):
    import opentimelineio as otio

    from otio_nodes.model import validate_model
    from otio_nodes.otio_io import model_to_otio

    model = linked_model("file:///media/plate.mov")
    validate_model(model)
    reference = model_to_otio(model).tracks[0][0].media_reference
    assert isinstance(reference, otio.schema.ExternalReference)
    assert reference.available_range is None
    assert reference.target_url == "file:///media/plate.mov"


def test_a_clip_longer_than_its_linked_file_fails_validation(tmp_path):
    from otio_nodes.model import validate_model

    model = linked_model("file:///media/plate.mov", duration=30)  # 30 frames of file, the clip needs more
    with pytest.raises(ValueError, match="too short"):
        validate_model(model)


@pytest.mark.skipif(_ffprobe() is None, reason="ffmpeg is not available")
def test_real_ffprobe_measures_a_real_file_and_gives_none_for_a_missing_one(tmp_path):
    from otio_nodes.media import ffprobe_seconds

    video = tmp_path / "two_seconds.mov"
    FfmpegEncoder().slate({"title": "x", "subtitle": "", "body": ""}, video, 48, 24.0)
    assert ffprobe_seconds(video) == pytest.approx(2.0, abs=0.1)
    assert ffprobe_seconds(tmp_path / "missing.mov") is None


def one_track_model(*clips):
    return {"rate": 24, "tracks": [{"clips": list(clips)}]}


def test_linked_files_lists_each_existing_linked_file_once(tmp_path):
    from otio_nodes.media import linked_files

    plate = tmp_path / "plate.mp4"
    plate.write_bytes(b"x")
    link = lambda url, key="": {"media": {"url": url, "start": 0, "duration": None, "key": key}}  # noqa: E731
    model = one_track_model(
        link(str(plate)), link(str(plate)), link("gone.mp4"), link("slate.mov", "griptape:slate"), {"media": None}
    )
    found = linked_files(model, lambda url: Path(url) if Path(url).is_absolute() else tmp_path / url)
    assert found == {str(plate): plate}, "nothing for a missing file, a generated slate or a clip with no media"


class ProxyEncoder:
    def proxy(self, source, target, on_progress=None, seconds=None):
        for done in (0.25, 1.0):
            if on_progress:
                on_progress(done)
        target.write_bytes(b"proxy")


def test_viewer_proxy_is_made_whole_once_and_never_written_over(tmp_path):
    from otio_nodes.media import make_viewer_proxy, viewer_proxy_path

    source = tmp_path / "dog pounce.mp4"
    source.write_bytes(b"original")
    folder = tmp_path / "previews"
    target = viewer_proxy_path(source, folder)
    assert target.parent == folder and target.name.startswith("dog pounce_") and target.suffix == ".mp4"
    seen = []
    make_viewer_proxy(source, target, ProxyEncoder(), seen.append)  # pyright: ignore[reportArgumentType]
    assert target.read_bytes() == b"proxy" and seen == [0.25, 1.0]
    assert source.read_bytes() == b"original", "the source is only read"
    assert [p.name for p in folder.iterdir()] == [target.name], "no partial file is left behind"
    assert viewer_proxy_path(source, folder) == target, "the same file always has the same copy"
    source.write_bytes(b"a different file")
    assert viewer_proxy_path(source, folder) != target, "a changed source gets its own copy"


def test_a_failed_viewer_proxy_leaves_nothing_behind(tmp_path):
    from otio_nodes.media import make_viewer_proxy

    class Failing:
        def proxy(self, source, target, on_progress=None, seconds=None):
            target.write_bytes(b"half")
            msg = "ffmpeg failed: nope"
            raise ValueError(msg)

    source = tmp_path / "a.mp4"
    source.write_bytes(b"x")
    target = tmp_path / "previews" / "a_copy.mp4"
    with pytest.raises(ValueError, match="nope"):
        make_viewer_proxy(source, target, Failing())  # pyright: ignore[reportArgumentType]
    assert list((tmp_path / "previews").iterdir()) == []


def test_viewer_proxy_from_real_ffmpeg_reports_progress_and_keeps_the_length(tmp_path):
    from otio_nodes.media import FfmpegEncoder, ffprobe_seconds, make_viewer_proxy, viewer_proxy_path

    source = tmp_path / "plate.mp4"
    try:
        encoder = FfmpegEncoder()
        encoder._run(
            ["-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=24:duration=3", "-pix_fmt", "yuv420p", str(source)]
        )
    except ValueError:
        pytest.skip("ffmpeg is not available")
    target = viewer_proxy_path(source, tmp_path / "previews")
    seen: list[float] = []
    make_viewer_proxy(source, target, encoder, seen.append)
    assert target.exists() and abs((ffprobe_seconds(target) or 0) - 3) < 0.2
    assert seen and seen[-1] > 0.9 and seen == sorted(seen), "progress only goes forward and reaches the end"


def test_audio_files_get_an_m4a_viewer_copy_that_keeps_the_length(tmp_path):
    from otio_nodes.media import FfmpegEncoder, ffprobe_seconds, make_viewer_proxy, viewer_proxy_path

    source = tmp_path / "line.aiff"
    try:
        encoder = FfmpegEncoder()
        encoder._run(["-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(source)])
    except ValueError:
        pytest.skip("ffmpeg is not available")
    target = viewer_proxy_path(source, tmp_path / "previews")
    assert target.suffix == ".m4a"
    seen: list[float] = []
    make_viewer_proxy(source, target, encoder, seen.append)
    assert target.exists() and abs((ffprobe_seconds(target) or 0) - 2) < 0.2
    assert source.stat().st_size > 0 and [p.name for p in target.parent.iterdir()] == [target.name]
