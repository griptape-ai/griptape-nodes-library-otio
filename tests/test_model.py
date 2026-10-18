import pytest

from otio_nodes.breakdown import breakdown
from otio_nodes.fountain import parse
from otio_nodes.model import build_model, derive_markers, total_frames, validate_model

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


def make_model() -> dict:
    return build_model(breakdown(parse(TEXT)))


def test_tracks_and_shots_are_laid_end_to_end():
    model = make_model()
    shots = model["tracks"][0]["clips"]
    assert model["tracks"][0]["role"] == "shots"
    assert shots[0]["start"] == 0
    for before, after in zip(shots, shots[1:], strict=False):
        assert after["start"] == before["start"] + before["duration"]
    assert total_frames(model) == shots[-1]["start"] + shots[-1]["duration"]


def test_speaker_tracks_in_order_of_appearance_plus_empty_sfx_and_audio():
    names = [t["name"] for t in make_model()["tracks"]]
    assert names == ["Shots", "JACK", "JILL (V.O.)", "SFX", "Audio"]
    tracks = {t["name"]: t for t in make_model()["tracks"]}
    assert tracks["SFX"]["clips"] == [] and tracks["Audio"]["clips"] == []


def test_dialogue_clip_sits_inside_its_shot():
    model = make_model()
    shot = model["tracks"][0]["clips"][0]
    line = model["tracks"][1]["clips"][0]
    assert line["meta"]["shot"] == shot["id"]
    assert shot["start"] <= line["start"]
    assert line["start"] + line["duration"] <= shot["start"] + shot["duration"]


def test_whole_frames_only():
    model = make_model()
    for track in model["tracks"]:
        for clip in track["clips"]:
            assert isinstance(clip["start"], int) and isinstance(clip["duration"], int)
    validate_model(model)


def test_validate_reports_overlap_bad_times_and_unknown_role():
    model = make_model()
    model["tracks"][1]["clips"].append(
        {"id": "x", "name": "x", "start": 0, "duration": 5, "description": "", "color": "", "enabled": True, "meta": {}}
    )
    model["tracks"][2]["role"] = "bogus"
    model["tracks"][3]["clips"].append(
        {
            "id": "y",
            "name": "y",
            "start": 1.5,
            "duration": 0,
            "description": "",
            "color": "",
            "enabled": True,
            "meta": {},
        }
    )
    with pytest.raises(ValueError) as error:
        validate_model(model)
    message = str(error.value)
    assert "overlaps" in message
    assert "role must be one of" in message
    assert "whole frames" in message


def test_derived_markers_follow_the_shots():
    model = make_model()
    markers = derive_markers(model)
    kinds = [m["kind"] for m in markers]
    assert kinds.count("sequence") == 2
    assert kinds.count("scene") == 2
    assert kinds.count("note") == 1
    first_sequence = next(m for m in markers if m["kind"] == "sequence")
    shots = model["tracks"][0]["clips"]
    assert first_sequence["start"] == 0
    assert first_sequence["duration"] == shots[0]["duration"] + shots[1]["duration"]

    shots[0]["duration"] += 24
    for later in shots[1:]:
        later["start"] += 24
    resized = next(m for m in derive_markers(model) if m["kind"] == "sequence")
    assert resized["duration"] == first_sequence["duration"] + 24


def test_scene_marker_colors_by_int_ext():
    colors = {m["name"]: m["color"] for m in derive_markers(make_model()) if m["kind"] == "scene"}
    assert colors == {"INT. ROOM - DAY": "ORANGE", "EXT. YARD - NIGHT": "GREEN"}
