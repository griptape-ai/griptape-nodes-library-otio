from pathlib import Path

import opentimelineio as otio
import pytest

from otio_nodes.breakdown import breakdown
from otio_nodes.fountain import parse
from otio_nodes.model import build_model, derive_markers, total_frames
from otio_nodes.otio_io import (
    METADATA_KEY,
    from_json,
    model_to_otio,
    next_version_path,
    otio_to_model,
    read_otio,
    to_json,
    write_otio,
)

TEXT = """Title: Test

INT. ROOM - DAY

JACK
Hello there my good friend today.

CLOSE UP of Jack. [[check eyes]]

CUT TO:

EXT. YARD - NIGHT

JILL (V.O.)
Hi.
"""
SCRIPT = Path("/Volumes/griptape/jonh-and-his-dog/10_preproduction/script/jonhAndHisDog_script_v002.fountain")


def make_model(text: str = TEXT) -> dict:
    return build_model(breakdown(parse(text)))


def test_timeline_structure_and_duration():
    model = make_model()
    timeline = model_to_otio(model)
    assert timeline.name == "Test"
    assert [t.name for t in timeline.tracks] == ["Shots", "JACK", "JILL (V.O.)", "SFX", "Audio"]
    assert timeline.tracks[0].kind == otio.schema.TrackKind.Video
    assert timeline.tracks[1].kind == otio.schema.TrackKind.Audio
    assert timeline.duration().value == total_frames(model) or timeline.duration().rescaled_to(
        24
    ).value == total_frames(model)
    assert timeline.duration().rate in (24.0, 24)


def test_clips_use_missing_reference_with_ranges_in_frames():
    timeline = model_to_otio(make_model())
    clip = timeline.tracks[0][0]
    assert isinstance(clip.media_reference, otio.schema.MissingReference)
    assert clip.source_range.start_time.rate == 24
    assert clip.source_range.duration.value == clip.media_reference.available_range.duration.value


def test_gaps_place_dialogue_at_its_position():
    model = make_model()
    timeline = model_to_otio(model)
    jill_track = timeline.tracks[2]
    jill_clip = model["tracks"][2]["clips"][0]
    assert isinstance(jill_track[0], otio.schema.Gap)
    assert jill_track.range_of_child_at_index(1).start_time.value == jill_clip["start"]


def test_namespaced_metadata_only():
    timeline = model_to_otio(make_model())
    clip = timeline.tracks[0][0]
    assert set(clip.metadata) == {METADATA_KEY}
    assert clip.metadata[METADATA_KEY]["kind"] == "shot"
    assert clip.metadata[METADATA_KEY]["sequence"] == 1
    assert set(timeline.metadata) == {METADATA_KEY}


def test_markers_are_ranged_and_colored():
    timeline = model_to_otio(make_model())
    markers = timeline.tracks[0].markers
    kinds = [m.metadata[METADATA_KEY]["kind"] for m in markers]
    assert kinds.count("sequence") == 2 and kinds.count("scene") == 2 and kinds.count("note") == 1
    sequence = next(m for m in markers if m.metadata[METADATA_KEY]["kind"] == "sequence")
    assert sequence.color == otio.schema.MarkerColor.PURPLE
    assert sequence.marked_range.duration.value > 0
    note = next(m for m in markers if m.metadata[METADATA_KEY]["kind"] == "note")
    assert note.comment == "check eyes"


def test_disabled_clip_and_clip_color_survive():
    model = make_model()
    model["tracks"][0]["clips"][0]["enabled"] = False
    timeline = model_to_otio(model)
    clip = timeline.tracks[0][0]
    assert clip.enabled is False
    assert clip.color is not None


def test_round_trip_restores_the_model():
    model = make_model()
    model["tracks"][3]["clips"].append(
        {
            "id": "sfx-1",
            "name": "car crash",
            "start": 10,
            "duration": 24,
            "description": "loud",
            "color": "#ff0000",
            "enabled": False,
            "media": None,
            "meta": {"kind": "sfx"},
        }
    )
    model["markers"].append({"id": "m1", "name": "check", "start": 5, "duration": 12, "color": "BLUE", "comment": "hi"})
    back = from_json(to_json(model))
    assert back == model


def test_derived_markers_are_not_read_back_as_user_markers():
    back = from_json(to_json(make_model()))
    assert back["markers"] == []
    assert len(derive_markers(back)) > 0


def test_edit_then_write_updates_markers():
    model = make_model()
    model["tracks"][0]["clips"][0]["duration"] += 12
    for later in model["tracks"][0]["clips"][1:]:
        later["start"] += 12
    markers = model_to_otio(model).tracks[0].markers
    sequence = next(m for m in markers if m.metadata[METADATA_KEY]["kind"] == "sequence")
    assert sequence.marked_range.start_time.value == 0


def test_foreign_otio_is_readable():
    timeline = otio.schema.Timeline(name="foreign")
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    rate = 25.0
    track.append(
        otio.schema.Gap(
            source_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, rate), otio.opentime.RationalTime(10, rate)
            )
        )
    )
    track.append(
        otio.schema.Clip(
            name="plate",
            source_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(100, rate), otio.opentime.RationalTime(50, rate)
            ),
        )
    )
    track.append(otio.schema.Transition(name="dissolve"))
    track.markers.append(
        otio.schema.Marker(
            name="note",
            marked_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(5, rate), otio.opentime.RationalTime(0, rate)
            ),
            color=otio.schema.MarkerColor.RED,
        )
    )
    timeline.tracks.append(track)
    model = otio_to_model(timeline)
    clip = model["tracks"][0]["clips"][0]
    assert model["rate"] == 25.0
    assert (clip["name"], clip["start"], clip["duration"]) == ("plate", 10, 50)
    assert model["tracks"][0]["role"] == "shots"
    assert model["markers"][0]["start"] == 5 and model["markers"][0]["duration"] == 1
    assert any("transition" in w for w in model["warnings"])


def test_other_rates_are_rescaled():
    timeline = otio.schema.Timeline()
    track = otio.schema.Track(kind=otio.schema.TrackKind.Video)
    track.append(
        otio.schema.Clip(
            name="a",
            source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0, 48), otio.opentime.RationalTime(96, 48)),
        )
    )
    timeline.tracks.append(track)
    timeline.metadata[METADATA_KEY] = {"rate": 24.0}
    assert otio_to_model(timeline)["tracks"][0]["clips"][0]["duration"] == 48


def test_write_refuses_to_overwrite_and_reads_back(tmp_path):
    model = make_model()
    path = write_otio(model, tmp_path / "out_v001.otio")
    assert path.exists()
    with pytest.raises(FileExistsError):
        write_otio(model, path)
    assert read_otio(path) == model


def test_next_version_path(tmp_path):
    assert next_version_path(tmp_path, "film").name == "film_v001.otio"
    (tmp_path / "film_v001.otio").write_text("x")
    (tmp_path / "film_v002.otio").write_text("x")
    assert next_version_path(tmp_path, "film").name == "film_v003.otio"


def test_invalid_model_is_rejected_before_writing(tmp_path):
    model = make_model()
    model["tracks"][0]["clips"][0]["duration"] = 0
    with pytest.raises(ValueError, match="Invalid timeline"):
        write_otio(model, tmp_path / "bad.otio")
    assert not (tmp_path / "bad.otio").exists()


@pytest.mark.skipif(not SCRIPT.exists(), reason="project script not available")
def test_real_script_round_trips_and_has_a_sensible_length(tmp_path):
    model = make_model(SCRIPT.read_text(encoding="utf-8"))
    seconds = total_frames(model) / model["rate"]
    assert 60 < seconds < 400
    path = write_otio(model, tmp_path / "jonh_v001.otio")
    assert read_otio(path) == model


def test_markers_on_clips_and_on_the_timeline_are_reported_when_dropped():
    timeline = model_to_otio(make_model())
    timeline.tracks[0][0].markers.append(otio.schema.Marker(name="clip marker"))
    timeline.tracks.markers.append(otio.schema.Marker(name="timeline marker"))
    warnings = otio_to_model(timeline)["warnings"]
    assert any("clip marker" not in w and "marker(s) on clip" in w for w in warnings)
    assert any("whole timeline" in w for w in warnings)
