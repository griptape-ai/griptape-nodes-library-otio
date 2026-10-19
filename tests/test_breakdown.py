from pathlib import Path

import pytest

from otio_nodes.breakdown import BreakdownSettings, breakdown, dialogue_seconds, find_cue
from otio_nodes.fountain import parse

SCRIPT = Path("/Volumes/griptape/jonh-and-his-dog/10_preproduction/script/jonhAndHisDog_script_v002.fountain")


def run(text: str, **settings) -> dict:
    return breakdown(parse(text), BreakdownSettings(**settings))


def test_find_cue_is_case_sensitive_and_prefers_longest():
    cues = BreakdownSettings().shot_cues
    assert find_cue("EXTREME WIDE SHOT of the house.", cues) == "EXTREME WIDE SHOT"
    assert find_cue("WIDE SHOT of the street.", cues) == "WIDE SHOT"
    assert find_cue("A wide shot of the street.", cues) == ""
    assert find_cue("WIDE SHOTS everywhere", cues) == ""


def test_dialogue_seconds_uses_rate_floor_and_pause():
    settings = BreakdownSettings(words_per_second=2.0, line_pause=0.5, min_line_seconds=1.0)
    assert dialogue_seconds("one two three four", settings) == pytest.approx(2.5)
    assert dialogue_seconds("hi", settings) == pytest.approx(1.5)


def test_cue_starts_a_new_shot_in_the_same_sequence():
    shots = run("INT. ROOM - DAY\n\nJack sits.\n\nCLOSE UP of Jack.\n\nWIDE SHOT of the room.\n")["shots"]
    assert [s["cue"] for s in shots] == ["", "CLOSE UP", "WIDE SHOT"]
    assert {s["sequence"] for s in shots} == {1}


def test_action_without_cue_extends_the_current_shot():
    shots = run("INT. ROOM - DAY\n\nWIDE SHOT of the room.\n\nJack waves.\n")["shots"]
    assert len(shots) == 1
    assert shots[0]["description"] == "WIDE SHOT of the room. Jack waves."


def test_transition_starts_a_new_sequence_even_mid_scene():
    text = "INT. ROOM - DAY\n\nJack sits.\n\nCUT TO:\n\nANOTHER ANGLE of the room.\n"
    shots = run(text)["shots"]
    assert [s["sequence"] for s in shots] == [1, 2]
    assert shots[0]["scene"] == shots[1]["scene"]


def test_switching_int_ext_starts_a_new_sequence_but_same_kind_does_not():
    text = "INT. ROOM - DAY\n\nA.\n\nINT. HALL - DAY\n\nB.\n\nEXT. YARD - DAY\n\nC.\n"
    assert [s["sequence"] for s in run(text)["shots"]] == [1, 1, 2]


def test_dialogue_belongs_to_the_shot_it_follows():
    text = "INT. ROOM - DAY\n\nJACK\nHello there my friend.\n\nCLOSE UP of Jack.\n\nJACK\nBye.\n"
    shots = run(text)["shots"]
    assert [len(s["dialogue"]) for s in shots] == [1, 1]
    assert shots[0]["cue"] == ""


def test_durations_from_dialogue_or_defaults():
    text = "INT. ROOM - DAY\n\nSilent action.\n\nCLOSE UP of Jack.\n\nJACK\nOne two three four five.\n"
    shots = run(text, words_per_second=1.0, line_pause=0.0, min_shot_seconds=2.0, default_shot_seconds=3.0)["shots"]
    assert shots[0]["seconds"] == 3.0
    assert shots[1]["seconds"] == pytest.approx(5.0)


def test_min_shot_seconds_applies_to_short_dialogue():
    text = "INT. ROOM - DAY\n\nJACK\nHi.\n"
    shot = run(text, line_pause=0.0, min_line_seconds=0.5, min_shot_seconds=2.0)["shots"][0]
    assert shot["seconds"] == 2.0


def test_notes_travel_with_the_shot():
    shot = run("INT. ROOM - DAY [[scene note]]\n\nJack waves [[wave note]].\n")["shots"][0]
    assert shot["notes"] == ["scene note", "wave note"]


def test_invalid_settings_raise():
    with pytest.raises(ValueError, match="rate"):
        BreakdownSettings(rate=0).validate()


def test_settings_round_trip_ignores_unknown_keys():
    settings = BreakdownSettings.from_dict({"rate": 25.0, "bogus": 1})
    assert settings.rate == 25.0
    assert BreakdownSettings.from_dict(settings.to_dict()) == settings


@pytest.mark.skipif(not SCRIPT.exists(), reason="project script not available")
def test_real_script_v002_sequences_and_shots():
    result = breakdown(parse(SCRIPT.read_text(encoding="utf-8")))
    shots = result["shots"]
    assert max(s["sequence"] for s in shots) == 8
    cues = [s["cue"] for s in shots]
    assert cues.count("WIDE SHOT") >= 5
    assert "EXTREME WIDE SHOT" in cues
    assert all(s["seconds"] > 0 for s in shots)
    assert sum(len(s["dialogue"]) for s in shots) == 34


def test_a_note_in_its_own_paragraph_reaches_the_next_shot():
    shots = breakdown(parse("INT. ROOM - DAY\n\n[[scene note]]\n\nRain falls.\n\n[[late note]]\n"))["shots"]
    assert shots[0]["notes"] == ["scene note", "late note"]


def test_a_note_above_a_scene_heading_goes_with_the_next_scene():
    shots = breakdown(
        parse("INT. ROOM - DAY\n\nRain falls.\n\n[[for the yard]]\n\nEXT. YARD - NIGHT\n\nWind blows.\n")
    )["shots"]
    assert shots[0]["notes"] == []
    assert shots[1]["notes"] == ["for the yard"]
