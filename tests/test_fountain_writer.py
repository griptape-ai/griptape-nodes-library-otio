import copy
from pathlib import Path

from otio_nodes.breakdown import breakdown
from otio_nodes.fountain import parse
from otio_nodes.fountain_writer import write_fountain
from otio_nodes.model import build_model

SCRIPT = Path(__file__).parent / "fixtures" / "sample_script.fountain"

SAMPLE = """Title: Test Film
Author: Someone
Notes: First line
    second line

===

INT. KITCHEN - DAY #1A#

JACK stirs a pot. [[watch the steam]]

JACK (V.O.)
(quietly)
Hello there.

CUT TO:

EXT. YARD - NIGHT

WIDE SHOT of the yard.

JILL
Hi.

CUT TO:

ANOTHER ANGLE of the yard.

JILL
Again.
"""


def model_of(text: str) -> dict:
    return build_model(breakdown(parse(text)))


def facts(parsed: dict) -> dict:
    elements = parsed["elements"]
    return {
        "title": parsed["title_page"],
        "headings": [e["text"] for e in elements if e["type"] == "scene_heading"],
        "numbers": [e["scene_number"] for e in elements if e["type"] == "scene_heading"],
        "dialogue": [
            (e["character"], e["extension"], e["parentheticals"], e["text"])
            for e in elements
            if e["type"] == "dialogue"
        ],
        "transitions": [e["text"] for e in elements if e["type"] == "transition"],
    }


def shot(model: dict, index: int) -> dict:
    return model["tracks"][0]["clips"][index]


def test_a_script_survives_the_trip_through_a_timeline():
    written = write_fountain(model_of(SAMPLE))
    assert facts(parse(written)) == facts(parse(SAMPLE))


def test_title_page_and_scene_numbers_are_written():
    written = write_fountain(model_of(SAMPLE))
    assert written.startswith("Title: Test Film\nAuthor: Someone\nNotes:\n   First line\n   second line\n\n===\n\n")
    assert "INT. KITCHEN - DAY #1A#" in written


def test_script_notes_are_kept():
    parsed = parse(write_fountain(model_of(SAMPLE)))
    action = next(e for e in parsed["elements"] if e["type"] == "action")
    assert action["notes"] == ["watch the steam"]
    assert "[[" not in action["text"]


def test_a_cut_inside_a_scene_does_not_repeat_the_heading():
    text = "INT. ROOM - DAY\n\nJack sits.\n\nCUT TO:\n\nANOTHER ANGLE of the room.\n"
    written = write_fountain(model_of(text))
    assert written.count("INT. ROOM - DAY") == 1
    assert "CUT TO:" in written
    assert facts(parse(written))["transitions"] == ["CUT TO:"]


def test_a_heading_that_is_not_int_or_ext_is_forced():
    parsed = parse(write_fountain(model_of(".UNDERWATER - DAY\n\nBubbles rise.\n")))
    assert [e["text"] for e in parsed["elements"] if e["type"] == "scene_heading"] == ["UNDERWATER - DAY"]


def test_action_that_looks_like_something_else_is_forced():
    model = model_of("INT. ROOM - DAY\n\nJack sits.\n")
    shot(model, 0)["description"] = "INT. SOMEWHERE ELSE - NIGHT"
    parsed = parse(write_fountain(model))
    assert [e["type"] for e in parsed["elements"]] == ["scene_heading", "action"]
    shot(model, 0)["description"] = "THE END"
    assert [e["type"] for e in parse(write_fountain(model))["elements"]] == ["scene_heading", "action"]


def test_edited_text_is_carried_into_the_script():
    model = model_of(SAMPLE)
    shot(model, 0)["description"] = "JACK burns the pot."
    line = model["tracks"][1]["clips"][0]
    line["description"] = "Goodbye then."
    written = write_fountain(model)
    assert "JACK burns the pot." in written and "Goodbye then." in written
    assert "stirs a pot" not in written


def test_disabled_shots_and_lines_are_left_out():
    model = model_of(SAMPLE)
    shot(model, 0)["enabled"] = False
    written = write_fountain(model)
    assert "stirs a pot" not in written and "Hello there." not in written, "a disabled shot takes its dialogue with it"
    assert "INT. KITCHEN" not in written and "EXT. YARD - NIGHT" in written

    model = model_of(SAMPLE)
    model["tracks"][1]["clips"][0]["enabled"] = False
    assert "Hello there." not in write_fountain(model)


def test_a_deleted_shot_takes_its_scene_heading_when_it_was_the_only_one():
    model = model_of(SAMPLE)
    model["tracks"][0]["clips"] = [c for c in model["tracks"][0]["clips"] if c["meta"]["scene"] != 0]
    model["tracks"][1]["clips"] = [c for c in model["tracks"][1]["clips"] if c["meta"]["shot"] != "shot-001"]
    written = write_fountain(model)
    assert "INT. KITCHEN" not in written and "EXT. YARD - NIGHT" in written


def test_timing_notes_are_off_by_default_and_readable_back_when_on():
    model = model_of(SAMPLE)
    assert "[[" not in write_fountain(model).replace("[[watch the steam]]", "")
    written = write_fountain(model, include_timing=True)
    seconds = shot(model, 0)["duration"] / model["rate"]
    assert f"[[{seconds:.1f} s]]" in written
    assert facts(parse(written)) == facts(parse(SAMPLE)), "notes do not change what the script says"


def test_sound_clips_become_notes_in_the_shot_they_start_in():
    from otio_nodes.model import total_frames  # noqa: F401  (documents that clips use timeline frames)
    from tests.test_ops_helpers import add_sfx

    model = add_sfx(model_of(SAMPLE), "car crash", start=shot(model_of(SAMPLE), 1)["start"] + 5)
    assert "SFX" not in write_fountain(model)
    written = write_fountain(model, include_sfx=True)
    assert "[[SFX: car crash at 0:" in written
    wide = written.split("WIDE SHOT of the yard.")[1].split("\n\n")[0]
    assert "car crash" in wide, "it sits with the shot that was on screen when the clip starts"


def test_dialogue_without_its_shot_goes_to_the_shot_it_sits_inside():
    model = model_of(SAMPLE)
    line = model["tracks"][1]["clips"][0]
    line["meta"]["shot"] = "shot-that-was-deleted"
    assert "Hello there." in write_fountain(model)
    line["start"] = 10**9
    assert "Hello there." not in write_fountain(model), "a line outside every shot has nowhere to go"


def test_the_timeline_is_not_changed():
    model = model_of(SAMPLE)
    before = copy.deepcopy(model)
    write_fountain(model, include_timing=True, include_sfx=True)
    assert model == before


def test_a_timeline_with_no_shots_gives_only_the_title_page():
    model = model_of(SAMPLE)
    model["tracks"] = [t for t in model["tracks"] if t["role"] != "shots"]
    assert [e["type"] for e in parse(write_fountain(model))["elements"]] == ["page_break"], (
        "only the title page is left"
    )


def test_the_sample_script_comes_back_with_everything_that_was_said():
    original = parse(SCRIPT.read_text(encoding="utf-8"))
    back = parse(write_fountain(build_model(breakdown(original))))
    assert facts(back) == facts(original)
    assert len([e for e in back["elements"] if e["type"] == "dialogue"]) == 24


def test_a_forced_character_name_is_written_back_with_its_at_sign():
    text = write_fountain(build_model(breakdown(parse("INT. ROOM - DAY\n\n@McCLANE\nYippee.\n"))))
    assert "@McCLANE\nYippee." in text
    again = parse(text)
    assert [e["character"] for e in again["elements"] if e["type"] == "dialogue"] == ["McCLANE"]
